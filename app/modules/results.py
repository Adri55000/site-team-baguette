import re
from math import ceil
from app.database import get_db



class InvalidResultFormat(ValueError):
    """Format de résultat invalide."""
    pass


TIME_PATTERN = re.compile(r"^(\d+):([0-5]\d):([0-5]\d)$")


def parse_final_time(value: str):
    """
    Parse un résultat de match.

    Entrées acceptées :
    - HH:MM:SS (ex: 01:23:45)
    - DNF
    - DQ

    Retour :
    - (final_time, result_status)
      - final_time : int (secondes) ou None
      - result_status : 'DNF', 'DQ' ou None
    """

    if not value:
        raise InvalidResultFormat("Résultat manquant")

    value = value.strip().upper()

    # Cas DNF / DQ
    if value in ("DNF", "DQ"):
        return None, value

    # Cas HH:MM:SS
    match = TIME_PATTERN.match(value)
    if not match:
        raise InvalidResultFormat(
            "Format invalide. Utiliser HH:MM:SS ou DNF/DQ."
        )

    hours, minutes, seconds = map(int, match.groups())

    total_seconds = hours * 3600 + minutes * 60 + seconds

    return total_seconds, None

def _resolve_from_series_source(series_row, source_type: str):
    """
    Détermine l'équipe à propager depuis une série source.
    - winner -> winner_team_id
    - loser  -> l'autre équipe
    Retourne None si indéterminable (égalité, série incomplète, type inconnu).
    """
    winner = series_row["winner_team_id"]
    t1 = series_row["team1_id"]
    t2 = series_row["team2_id"]

    if not winner:
        return None  # égalité ou série non gagnée

    if source_type == "winner":
        return winner

    if source_type == "loser":
        if not t1 or not t2:
            return None
        return t2 if winner == t1 else t1

    return None


def update_series_result(series_id: int):
    """
    Recalcule et met à jour le vainqueur d'une série (BO),
    puis propage automatiquement winner/loser vers les séries dépendantes.

    Garanties :
    - Idempotent
    - La vérité métier repose uniquement sur les matchs complétés
    - Ne crée aucune série
    - Ne remplit que les slots vides, SAUF en cas de changement du résultat :
        -> on "dé-propage" uniquement les slots qui contiennent exactement
           l'ancienne équipe propagée, pour éviter les incohérences après
           correction/suppression de match
    - N'écrase jamais une saisie manuelle différente
    """

    db = get_db()

    # --- Récupération de la série (base) ---
    series = db.execute(
        """
        SELECT
            id,
            team1_id,
            team2_id,
            best_of
        FROM series
        WHERE id = ?
        """,
        (series_id,)
    ).fetchone()

    if not series:
        return

    # --- Snapshot état ancien (pour gérer suppression/correction de résultats) ---
    old_state = db.execute(
        """
        SELECT
            team1_id,
            team2_id,
            winner_team_id
        FROM series
        WHERE id = ?
        """,
        (series_id,)
    ).fetchone()

    team1_id = series["team1_id"]
    team2_id = series["team2_id"]

    # v1 : si la série n'a pas encore ses équipes (bracket précréé), on ne calcule rien
    if not team1_id or not team2_id:
        # si le winner était défini, on le vide (cohérence)
        db.execute(
            "UPDATE series SET winner_team_id = NULL WHERE id = ?",
            (series_id,)
        )

        # Si on passe de winner -> NULL, on peut devoir "dé-propager" ce qui avait été auto-propagé.
        if old_state and old_state["winner_team_id"]:
            old_t1 = old_state["team1_id"]
            old_t2 = old_state["team2_id"]
            old_winner = old_state["winner_team_id"]

            def old_resolve(src_type: str):
                if not old_winner:
                    return None
                if src_type == "winner":
                    return old_winner
                if src_type == "loser":
                    if not old_t1 or not old_t2:
                        return None
                    return old_t2 if old_winner == old_t1 else old_t1
                return None

            # clear team1 slots
            deps = db.execute(
                """
                SELECT id, source_team1_type
                FROM series
                WHERE source_team1_series_id = ?
                """,
                (series_id,)
            ).fetchall()

            for d in deps:
                old_team = old_resolve(d["source_team1_type"])
                if old_team:
                    db.execute(
                        """
                        UPDATE series
                        SET team1_id = NULL
                        WHERE id = ?
                          AND team1_id = ?
                        """,
                        (d["id"], old_team)
                    )

            # clear team2 slots
            deps = db.execute(
                """
                SELECT id, source_team2_type
                FROM series
                WHERE source_team2_series_id = ?
                """,
                (series_id,)
            ).fetchall()

            for d in deps:
                old_team = old_resolve(d["source_team2_type"])
                if old_team:
                    db.execute(
                        """
                        UPDATE series
                        SET team2_id = NULL
                        WHERE id = ?
                          AND team2_id = ?
                        """,
                        (d["id"], old_team)
                    )

        db.commit()
        return

    # --- Nombre de victoires nécessaires ---
    wins_needed = ceil(series["best_of"] / 2)

    # --- Comptage des victoires ---
    rows = db.execute(
        """
        SELECT
            mt.team_id,
            COUNT(*) AS wins
        FROM matches m
        JOIN match_teams mt ON mt.match_id = m.id
        WHERE m.series_id = ?
          AND m.is_completed = 1
          AND mt.is_winner = 1
        GROUP BY mt.team_id
        """,
        (series_id,)
    ).fetchall()

    wins = {row["team_id"]: row["wins"] for row in rows}

    # --- Détermination du vainqueur ---
    new_winner = None

    if wins.get(team1_id, 0) >= wins_needed:
        new_winner = team1_id
    elif wins.get(team2_id, 0) >= wins_needed:
        new_winner = team2_id

    # --- Mise à jour BDD winner ---
    db.execute(
        """
        UPDATE series
        SET winner_team_id = ?
        WHERE id = ?
        """,
        (new_winner, series_id)
    )

    # --- Relecture état source à jour ---
    source_series = db.execute(
        """
        SELECT
            team1_id,
            team2_id,
            winner_team_id
        FROM series
        WHERE id = ?
        """,
        (series_id,)
    ).fetchone()

    # --- Dé-propagation safe si changement de résultat ---
    if old_state and source_series:
        old_winner = old_state["winner_team_id"]
        old_t1 = old_state["team1_id"]
        old_t2 = old_state["team2_id"]

        def old_resolve(src_type: str):
            if not old_winner:
                return None
            if src_type == "winner":
                return old_winner
            if src_type == "loser":
                if not old_t1 or not old_t2:
                    return None
                return old_t2 if old_winner == old_t1 else old_t1
            return None

        # Si le winner change (y compris -> NULL), on nettoie les slots auto-propagés précédents
        if old_winner != source_series["winner_team_id"]:
            # clear team1 slots qui matchent exactement l'ancienne propagation
            deps = db.execute(
                """
                SELECT id, source_team1_type
                FROM series
                WHERE source_team1_series_id = ?
                """,
                (series_id,)
            ).fetchall()

            for d in deps:
                old_team = old_resolve(d["source_team1_type"])
                if old_team:
                    db.execute(
                        """
                        UPDATE series
                        SET team1_id = NULL
                        WHERE id = ?
                          AND team1_id = ?
                        """,
                        (d["id"], old_team)
                    )

            # clear team2 slots
            deps = db.execute(
                """
                SELECT id, source_team2_type
                FROM series
                WHERE source_team2_series_id = ?
                """,
                (series_id,)
            ).fetchall()

            for d in deps:
                old_team = old_resolve(d["source_team2_type"])
                if old_team:
                    db.execute(
                        """
                        UPDATE series
                        SET team2_id = NULL
                        WHERE id = ?
                          AND team2_id = ?
                        """,
                        (d["id"], old_team)
                    )

    # --- Propagation winner/loser vers les séries suivantes (sans jamais écraser) ---
    if source_series:
        # team1 slots dépendants
        deps = db.execute(
            """
            SELECT id, source_team1_type
            FROM series
            WHERE source_team1_series_id = ?
              AND team1_id IS NULL
            """,
            (series_id,)
        ).fetchall()

        for d in deps:
            team_to_set = _resolve_from_series_source(source_series, d["source_team1_type"])
            if team_to_set:
                db.execute(
                    "UPDATE series SET team1_id = ? WHERE id = ?",
                    (team_to_set, d["id"])
                )

        # team2 slots dépendants
        deps = db.execute(
            """
            SELECT id, source_team2_type
            FROM series
            WHERE source_team2_series_id = ?
              AND team2_id IS NULL
            """,
            (series_id,)
        ).fetchall()

        for d in deps:
            team_to_set = _resolve_from_series_source(source_series, d["source_team2_type"])
            if team_to_set:
                db.execute(
                    "UPDATE series SET team2_id = ? WHERE id = ?",
                    (team_to_set, d["id"])
                )

    db.commit()
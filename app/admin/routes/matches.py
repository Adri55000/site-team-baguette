from flask import (
    request,
    render_template,
    redirect,
    url_for,
    flash,
    abort,
    jsonify,
)
from app.auth.utils import login_required
from flask_babel import _

from .. import admin_bp
from app.database import get_db
from app.permissions.decorators import role_required

from app.modules.tournaments import get_tournament_phases

from app.modules import racetime as racetime_mod

@admin_bp.route("/matches")
@login_required
@role_required("admin")
def admin_matches():
    db = get_db()

    tournament_id = request.args.get("tournament_id", type=int)
    phase_id = request.args.get("phase_id", type=int)

    tournaments = db.execute(
        "SELECT id, name FROM tournaments ORDER BY created_at DESC"
    ).fetchall()

    if not tournament_id:
        return render_template(
            "admin/matches/index.html",
            tournaments=tournaments,
            selected_tournament=None,
            selected_phase_id=None
        )

    tournament = db.execute(
        "SELECT * FROM tournaments WHERE id = ?",
        (tournament_id,)
    ).fetchone()

    if not tournament:
        flash(_("Tournoi introuvable."), "error")
        return redirect(url_for("admin.admin_matches"))
        
    # ✅ Phases du tournoi (toutes, même si aucune série n'existe encore)
    phases = db.execute(
        """
        SELECT id, name, position, type
        FROM tournament_phases
        WHERE tournament_id = ?
        ORDER BY position
        """,
        (tournament_id,),
    ).fetchall()

    # ✅ Filtre optionnel sur la phase
    phase_filter_sql = ""
    params = [tournament_id]
    if phase_id:
        phase_filter_sql = " AND s.phase_id = ?"
        params.append(phase_id)        
        
    confrontations = db.execute(
        f"""
        SELECT
            s.id,
            s.phase_id,
            s.stage,
            s.best_of,
            s.winner_team_id,
            s.created_at,

            p.name AS phase_name,
            p.position AS phase_position,

            t1.name AS team1_name,
            t2.name AS team2_name,
            tw.name AS winner_name,

            COALESCE(mc.match_count, 0)     AS match_count,
            COALESCE(mp.matches_played, 0)  AS matches_played,
            COALESCE(w.team1_wins, 0)       AS team1_wins,
            COALESCE(w.team2_wins, 0)       AS team2_wins

        FROM series s
        JOIN tournament_phases p ON p.id = s.phase_id
        LEFT JOIN teams t1 ON t1.id = s.team1_id
        LEFT JOIN teams t2 ON t2.id = s.team2_id
        LEFT JOIN teams tw ON tw.id = s.winner_team_id

        -- total matchs (tous)
        LEFT JOIN (
            SELECT series_id, COUNT(*) AS match_count
            FROM matches
            GROUP BY series_id
        ) mc ON mc.series_id = s.id

        -- matchs terminés
        LEFT JOIN (
            SELECT series_id, COUNT(*) AS matches_played
            FROM matches
            WHERE is_completed = 1
            GROUP BY series_id
        ) mp ON mp.series_id = s.id

        -- wins (compte 1 win max par match)
        LEFT JOIN (
            SELECT
                m.series_id,
                COUNT(DISTINCT CASE WHEN mt.is_winner = 1 AND mt.team_id = s2.team1_id THEN m.id END) AS team1_wins,
                COUNT(DISTINCT CASE WHEN mt.is_winner = 1 AND mt.team_id = s2.team2_id THEN m.id END) AS team2_wins
            FROM matches m
            JOIN series s2 ON s2.id = m.series_id
            JOIN match_teams mt ON mt.match_id = m.id
            WHERE m.is_completed = 1
            GROUP BY m.series_id
        ) w ON w.series_id = s.id

        WHERE s.tournament_id = ?
        {phase_filter_sql}

        GROUP BY s.id
        ORDER BY s.created_at

        """,
        tuple(params)
    ).fetchall()

    tiebreaks = db.execute(
        """
        SELECT id, scheduled_at, is_completed
        FROM matches
        WHERE tournament_id = ?
          AND series_id IS NULL
        ORDER BY created_at
        """,
        (tournament_id,)
    ).fetchall()

    return render_template(
        "admin/matches/index.html",
        tournaments=tournaments,
        selected_tournament=tournament,
        selected_phase_id=phase_id,
        confrontations=confrontations,
        tiebreaks=tiebreaks,
        phases=phases
    )


@admin_bp.route("/confrontations/create", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_confrontation_create():
    db = get_db()

    tournament_id = request.args.get("tournament_id", type=int)
    prefill_phase_id = request.args.get("phase_id", type=int)  # ✅ préfill depuis le filtre
    if not tournament_id:
        flash(_("Tournoi manquant."), "error")
        return redirect(url_for("admin.admin_matches"))

    tournament = db.execute(
        "SELECT * FROM tournaments WHERE id = ?",
        (tournament_id,)
    ).fetchone()

    if not tournament:
        flash(_("Tournoi introuvable."), "error")
        return redirect(url_for("admin.admin_matches"))

    # 🔹 Récupération des phases du tournoi
    phases = get_tournament_phases(db, tournament_id)

    if not phases:
        flash(
            _("Impossible de créer une confrontation : aucune phase n'est définie pour ce tournoi."),
            "error"
        )
        return redirect(url_for("admin.admin_matches", tournament_id=tournament_id))

    # --- POST : création ---
    if request.method == "POST":
        phase_id = request.form.get("phase_id", type=int)
        stage = (request.form.get("stage") or "").strip()
        best_of = request.form.get("best_of", type=int)
        round_value = request.form.get("round", type=int)

        team1_id = request.form.get("team1_id", type=int)
        team2_id = request.form.get("team2_id", type=int)

        # ✅ sources (progression bracket)
        source_team1_series_id = request.form.get("source_team1_series_id", type=int)
        source_team2_series_id = request.form.get("source_team2_series_id", type=int)
        source_team1_type = (request.form.get("source_team1_type") or "").strip() or None
        source_team2_type = (request.form.get("source_team2_type") or "").strip() or None

        # 🔒 Validation phase
        if not phase_id:
            flash(_("Une phase doit être sélectionnée."), "error")
            return redirect(request.url)

        phase = db.execute(
            """
            SELECT id, type
            FROM tournament_phases
            WHERE id = ? AND tournament_id = ?
            """,
            (phase_id, tournament_id)
        ).fetchone()

        if not phase:
            flash(_("Phase invalide pour ce tournoi."), "error")
            return redirect(request.url)

        phase_type = phase["type"]
        is_bracket = phase_type in ("bracket_simple_elim", "bracket_double_elim")

        # 🔒 round n'a de sens que pour les brackets
        if not is_bracket:
            round_value = None

        # 🔹 Récupération des équipes inscrites (pour validation si nécessaire)
        teams = db.execute(
            """
            SELECT t.id
            FROM teams t
            JOIN tournament_teams tt ON tt.team_id = t.id
            WHERE tt.tournament_id = ?
            """,
            (tournament_id,)
        ).fetchall()
        team_ids = {t["id"] for t in teams}

        # ✅ Validation équipes :
        # - bracket : équipes optionnelles (draft autorisé)
        # - non-bracket : 2 équipes obligatoires + règles existantes
        if not is_bracket:
            if not team1_id or not team2_id:
                flash(_("Les deux équipes doivent être sélectionnées."), "error")
                return redirect(request.url)

            if team1_id == team2_id:
                flash(_("Les deux équipes doivent être différentes."), "error")
                return redirect(request.url)

            if team1_id not in team_ids or team2_id not in team_ids:
                flash(_("Les équipes doivent être inscrites au tournoi."), "error")
                return redirect(request.url)
        else:
            # bracket : si une équipe est renseignée, elle doit être inscrite
            if team1_id and team1_id not in team_ids:
                flash(_("Équipe A invalide (non inscrite au tournoi)."), "error")
                return redirect(request.url)
            if team2_id and team2_id not in team_ids:
                flash(_("Équipe B invalide (non inscrite au tournoi)."), "error")
                return redirect(request.url)
            if team1_id and team2_id and team1_id == team2_id:
                flash(_("Les deux équipes doivent être différentes."), "error")
                return redirect(request.url)

            # ✅ Validation sources : uniquement bracket
            if team1_id and source_team1_series_id:
                flash(_("Équipe A : choisissez une équipe OU une source, pas les deux."), "error")
                return redirect(request.url)
            if team2_id and source_team2_series_id:
                flash(_("Équipe B : choisissez une équipe OU une source, pas les deux."), "error")
                return redirect(request.url)

            if source_team1_series_id and source_team1_type not in ("winner", "loser"):
                flash(_("Équipe A : le type de source doit être winner ou loser."), "error")
                return redirect(request.url)
            if source_team2_series_id and source_team2_type not in ("winner", "loser"):
                flash(_("Équipe B : le type de source doit être winner ou loser."), "error")
                return redirect(request.url)

            # sources doivent appartenir au même tournoi + même phase (cohérence bracket)
            if source_team1_series_id:
                ok = db.execute(
                    """
                    SELECT 1
                    FROM series
                    WHERE id = ? AND tournament_id = ? AND phase_id = ?
                    """,
                    (source_team1_series_id, tournament_id, phase_id)
                ).fetchone()
                if not ok:
                    flash(_("Source A invalide (doit être dans la même phase et le même tournoi)."), "error")
                    return redirect(request.url)

            if source_team2_series_id:
                ok = db.execute(
                    """
                    SELECT 1
                    FROM series
                    WHERE id = ? AND tournament_id = ? AND phase_id = ?
                    """,
                    (source_team2_series_id, tournament_id, phase_id)
                ).fetchone()
                if not ok:
                    flash(_("Source B invalide (doit être dans la même phase et le même tournoi)."), "error")
                    return redirect(request.url)

        db.execute(
            """
            INSERT INTO series (
                tournament_id,
                phase_id,
                team1_id,
                team2_id,
                stage,
                best_of,
                round,
                source_team1_series_id,
                source_team2_series_id,
                source_team1_type,
                source_team2_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tournament_id,
                phase_id,
                team1_id,
                team2_id,
                stage,
                best_of,
                round_value,
                source_team1_series_id,
                source_team2_series_id,
                source_team1_type,
                source_team2_type
            )
        )
        db.commit()

        flash(_("Confrontation créée."), "success")
        return redirect(url_for("admin.admin_matches", tournament_id=tournament_id, phase_id=phase_id))

    # --- GET : affichage du formulaire ---
    teams = db.execute(
        """
        SELECT t.id, t.name
        FROM teams t
        JOIN tournament_teams tt ON tt.team_id = t.id
        WHERE tt.tournament_id = ?
        ORDER BY t.name
        """,
        (tournament_id,)
    ).fetchall()

    # ✅ candidats sources : seulement si une phase est pré-sélectionnée
    source_candidates = []
    if prefill_phase_id:
        source_candidates = db.execute(
            """
            SELECT id, round, stage
            FROM series
            WHERE tournament_id = ?
              AND phase_id = ?
            ORDER BY COALESCE(round, 9999), id
            """,
            (tournament_id, prefill_phase_id)
        ).fetchall()

    return render_template(
        "admin/matches/confrontation_form.html",
        tournament=tournament,
        teams=teams,
        phases=phases,
        selected_phase_id=prefill_phase_id,  # ✅ pour préselection
        series=None,
        teams_locked=False,
        source_candidates=source_candidates  # ✅ pour les selects de source (template)
    )


@admin_bp.route("/matches/confrontations/<int:series_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_confrontation_edit(series_id):
    db = get_db()

    series = db.execute(
        "SELECT * FROM series WHERE id = ?",
        (series_id,)
    ).fetchone()

    if not series:
        flash(_("Confrontation introuvable."), "error")
        return redirect(url_for("admin.admin_matches"))

    tournament = db.execute(
        "SELECT * FROM tournaments WHERE id = ?",
        (series["tournament_id"],)
    ).fetchone()

    if tournament["status"] == "finished":
        flash(_("Tournoi terminé : modification impossible."), "error")
        return redirect(url_for("admin.admin_matches", tournament_id=tournament["id"]))

    phases = get_tournament_phases(db, tournament["id"])

    match_count = db.execute(
        "SELECT COUNT(*) FROM matches WHERE series_id = ?",
        (series_id,)
    ).fetchone()[0]

    teams = db.execute(
        """
        SELECT t.id, t.name
        FROM teams t
        JOIN tournament_teams tt ON tt.team_id = t.id
        WHERE tt.tournament_id = ?
        ORDER BY t.name
        """,
        (tournament["id"],)
    ).fetchall()

    team_ids = {t["id"] for t in teams}

    if request.method == "POST":
        phase_id = request.form.get("phase_id", type=int) or series["phase_id"]
        stage = (request.form.get("stage") or "").strip()
        best_of = request.form.get("best_of", type=int) or series["best_of"]
        round_value = request.form.get("round", type=int)

        # ✅ sources (progression bracket)
        source_team1_series_id = request.form.get("source_team1_series_id", type=int)
        source_team2_series_id = request.form.get("source_team2_series_id", type=int)
        source_team1_type = (request.form.get("source_team1_type") or "").strip() or None
        source_team2_type = (request.form.get("source_team2_type") or "").strip() or None

        if not phase_id:
            flash(_("Une phase doit être sélectionnée."), "error")
            return redirect(request.url)

        phase = db.execute(
            """
            SELECT id, type
            FROM tournament_phases
            WHERE id = ? AND tournament_id = ?
            """,
            (phase_id, tournament["id"])
        ).fetchone()

        if not phase:
            flash(_("Phase invalide pour ce tournoi."), "error")
            return redirect(request.url)

        phase_type = phase["type"]
        is_bracket = phase_type in ("bracket_simple_elim", "bracket_double_elim")

        # 🔒 round n'a de sens que pour les brackets
        if not is_bracket:
            round_value = None

        # équipes / phase / round / sources modifiables uniquement si aucun match
        if match_count == 0:
            team1_id = request.form.get("team1_id", type=int)
            team2_id = request.form.get("team2_id", type=int)

            if not is_bracket:
                # non-bracket : 2 équipes obligatoires
                if not team1_id or not team2_id:
                    flash(_("Les deux équipes doivent être sélectionnées."), "error")
                    return redirect(request.url)

                if team1_id == team2_id:
                    flash(_("Les deux équipes doivent être différentes."), "error")
                    return redirect(request.url)

                if team1_id not in team_ids or team2_id not in team_ids:
                    flash(_("Les équipes doivent être inscrites au tournoi."), "error")
                    return redirect(request.url)

                # non-bracket : on ignore les sources, par sécurité
                source_team1_series_id = None
                source_team2_series_id = None
                source_team1_type = None
                source_team2_type = None

            else:
                # bracket : équipes optionnelles
                if team1_id and team1_id not in team_ids:
                    flash(_("Équipe A invalide (non inscrite au tournoi)."), "error")
                    return redirect(request.url)
                if team2_id and team2_id not in team_ids:
                    flash(_("Équipe B invalide (non inscrite au tournoi)."), "error")
                    return redirect(request.url)
                if team1_id and team2_id and team1_id == team2_id:
                    flash(_("Les deux équipes doivent être différentes."), "error")
                    return redirect(request.url)

                # ✅ Validation sources
                if team1_id and source_team1_series_id:
                    flash(_("Équipe A : choisissez une équipe OU une source, pas les deux."), "error")
                    return redirect(request.url)
                if team2_id and source_team2_series_id:
                    flash(_("Équipe B : choisissez une équipe OU une source, pas les deux."), "error")
                    return redirect(request.url)

                if source_team1_series_id and source_team1_type not in ("winner", "loser"):
                    flash(_("Équipe A : le type de source doit être winner ou loser."), "error")
                    return redirect(request.url)
                if source_team2_series_id and source_team2_type not in ("winner", "loser"):
                    flash(_("Équipe B : le type de source doit être winner ou loser."), "error")
                    return redirect(request.url)

                # pas d'auto-référence
                if source_team1_series_id == series_id or source_team2_series_id == series_id:
                    flash(_("Une confrontation ne peut pas dépendre d'elle-même."), "error")
                    return redirect(request.url)

                # sources doivent appartenir au même tournoi + même phase
                if source_team1_series_id:
                    ok = db.execute(
                        """
                        SELECT 1
                        FROM series
                        WHERE id = ? AND tournament_id = ? AND phase_id = ?
                        """,
                        (source_team1_series_id, tournament["id"], phase_id)
                    ).fetchone()
                    if not ok:
                        flash(_("Source A invalide (doit être dans la même phase et le même tournoi)."), "error")
                        return redirect(request.url)

                if source_team2_series_id:
                    ok = db.execute(
                        """
                        SELECT 1
                        FROM series
                        WHERE id = ? AND tournament_id = ? AND phase_id = ?
                        """,
                        (source_team2_series_id, tournament["id"], phase_id)
                    ).fetchone()
                    if not ok:
                        flash(_("Source B invalide (doit être dans la même phase et le même tournoi)."), "error")
                        return redirect(request.url)

            db.execute(
                """
                UPDATE series
                SET
                    phase_id = ?,
                    team1_id = ?,
                    team2_id = ?,
                    stage = ?,
                    best_of = ?,
                    round = ?,
                    source_team1_series_id = ?,
                    source_team2_series_id = ?,
                    source_team1_type = ?,
                    source_team2_type = ?
                WHERE id = ?
                """,
                (
                    phase_id,
                    team1_id,
                    team2_id,
                    stage,
                    best_of,
                    round_value,
                    source_team1_series_id,
                    source_team2_series_id,
                    source_team1_type,
                    source_team2_type,
                    series_id
                )
            )
        else:
            # 🔒 conservateur v1 : on ne change pas phase/round/teams/sources si matchs existent
            db.execute(
                """
                UPDATE series
                SET stage = ?, best_of = ?
                WHERE id = ?
                """,
                (stage, best_of, series_id)
            )

        db.commit()
        flash(_("Confrontation mise à jour."), "success")
        return redirect(url_for("admin.admin_matches", tournament_id=tournament["id"], phase_id=phase_id))

    # ✅ candidats sources pour le template (même phase que la série)
    source_candidates = db.execute(
        """
        SELECT id, round, stage
        FROM series
        WHERE tournament_id = ?
          AND phase_id = ?
          AND id != ?
        ORDER BY COALESCE(round, 9999), id
        """,
        (tournament["id"], series["phase_id"], series_id)
    ).fetchall()

    return render_template(
        "admin/matches/confrontation_form.html",
        series=series,
        teams=teams,
        tournament=tournament,
        phases=phases,
        selected_phase_id=series["phase_id"],
        teams_locked=(match_count > 0),
        source_candidates=source_candidates
    )


@admin_bp.route("/matches/create", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_match_create():
    db = get_db()

    series_id = request.args.get("series_id", type=int) \
        or request.form.get("series_id", type=int)

    tournament_id = request.args.get("tournament_id", type=int) \
        or request.form.get("tournament_id", type=int)

    series = None
    tournament = None

    # --- Contexte ---
    if series_id:
        series = db.execute(
            """
            SELECT
                s.*,
                t1.name AS team1_name,
                t2.name AS team2_name
            FROM series s
            LEFT JOIN teams t1 ON t1.id = s.team1_id
            LEFT JOIN teams t2 ON t2.id = s.team2_id
            WHERE s.id = ?
            """,
            (series_id,)
        ).fetchone()

        if not series:
            flash(_("Confrontation introuvable."), "error")
            return redirect(url_for("admin.admin_matches"))

        tournament = db.execute(
            "SELECT * FROM tournaments WHERE id = ?",
            (series["tournament_id"],)
        ).fetchone()
        tournament_id = tournament["id"]

    else:
        tournament = db.execute(
            "SELECT * FROM tournaments WHERE id = ?",
            (tournament_id,)
        ).fetchone()

        if not tournament:
            flash(_("Tournoi introuvable."), "error")
            return redirect(url_for("admin.admin_matches"))

    if tournament["status"] == "finished":
        flash(_("Tournoi terminé : création impossible."), "error")
        return redirect(url_for("admin.admin_matches", tournament_id=tournament_id))

    # Équipes disponibles (pour tie-break)
    teams = db.execute(
        """
        SELECT t.id, t.name
        FROM teams t
        JOIN tournament_teams tt ON tt.team_id = t.id
        WHERE tt.tournament_id = ?
        ORDER BY t.name
        """,
        (tournament_id,)
    ).fetchall()
    team_ids = {t["id"] for t in teams}

    # --- POST ---
    if request.method == "POST":
        scheduled_at = request.form.get("scheduled_at")

        racetime_room_raw = request.form.get("racetime_room", "").strip()
        racetime_room = racetime_room_raw or None

        # Création du match
        cur = db.execute(
            """
            INSERT INTO matches (tournament_id, series_id, scheduled_at, racetime_room)
            VALUES (?, ?, ?, ?)
            """,
            (tournament_id, series_id, scheduled_at, racetime_room)
        )
        match_id = cur.lastrowid
        # Création des lignes match_teams pour une confrontation
        if series_id:
            db.execute(
                """
                INSERT INTO match_teams (match_id, team_id)
                VALUES (?, ?)
                """,
                (match_id, series["team1_id"])
            )
            db.execute(
                """
                INSERT INTO match_teams (match_id, team_id)
                VALUES (?, ?)
                """,
                (match_id, series["team2_id"])
            )

        # Tie-break multi-équipes
        if not series_id:
            selected_teams = request.form.getlist("team_ids")
            selected_teams = [int(t) for t in selected_teams if t.isdigit()]

            if len(selected_teams) < 2:
                flash(_("Un tie-break doit contenir au moins 2 équipes."), "error")
                db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
                db.commit()
                return redirect(request.url)

            if not all(tid in team_ids for tid in selected_teams):
                flash(_("Toutes les équipes doivent être inscrites au tournoi."), "error")
                db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
                db.commit()
                return redirect(request.url)

            for tid in selected_teams:
                db.execute(
                    """
                    INSERT INTO match_teams (match_id, team_id)
                    VALUES (?, ?)
                    """,
                    (match_id, tid)
                )

        db.commit()
        flash(_("Match créé."), "success")

        if series_id:
            return redirect(
                url_for("admin.admin_confrontation_matches", series_id=series_id)
            )

        return redirect(
            url_for("admin.admin_matches", tournament_id=tournament_id)
        )

    return render_template(
        "admin/matches/match_form.html",
        series=series,
        tournament=tournament,
        teams=teams
    )


@admin_bp.route("/matches/confrontations/<int:series_id>/matches")
@login_required
@role_required("admin")
def admin_confrontation_matches(series_id):
    db = get_db()

    series = db.execute(
        """
        SELECT
            s.*,
            p.name AS phase_name,
            p.position AS phase_position,
            t1.name AS team1_name,
            t2.name AS team2_name,
            tw.name AS winner_name,

            SUM(
                CASE
                    WHEN mt.team_id = s.team1_id AND mt.is_winner = 1 THEN 1
                    ELSE 0
                END
            ) AS team1_wins,

            SUM(
                CASE
                    WHEN mt.team_id = s.team2_id AND mt.is_winner = 1 THEN 1
                    ELSE 0
                END
            ) AS team2_wins

        FROM series s
        JOIN tournament_phases p ON p.id = s.phase_id
        LEFT JOIN teams t1 ON t1.id = s.team1_id
        LEFT JOIN teams t2 ON t2.id = s.team2_id
        LEFT JOIN teams tw ON tw.id = s.winner_team_id

        LEFT JOIN matches m
            ON m.series_id = s.id
            AND m.is_completed = 1

        LEFT JOIN match_teams mt
            ON mt.match_id = m.id

        WHERE s.id = ?
        GROUP BY s.id
        """,
        (series_id,)
    ).fetchone()


    if not series:
        flash(_("Confrontation introuvable."), "error")
        return redirect(url_for("admin.admin_matches"))

    matches = db.execute(
        """
        SELECT *
        FROM matches
        WHERE series_id = ?
        ORDER BY match_index, created_at
        """,
        (series_id,)
    ).fetchall()

    return render_template(
        "admin/matches/confrontation_matches.html",
        series=series,
        matches=matches
    )
    
    
@admin_bp.route(
    "/matches/<int:match_id>/edit",
    methods=["GET", "POST"]
)
@login_required
@role_required("admin")
def admin_match_edit(match_id):
    db = get_db()

    match = db.execute(
        "SELECT * FROM matches WHERE id = ?",
        (match_id,)
    ).fetchone()

    if not match:
        flash(_("Match introuvable."), "error")
        return redirect(url_for("admin.admin_matches"))

    tournament = db.execute(
        "SELECT * FROM tournaments WHERE id = ?",
        (match["tournament_id"],)
    ).fetchone()

    if tournament["status"] == "finished":
        flash(_("Tournoi terminé : modification impossible."), "error")
        return redirect(
            url_for("admin.admin_matches", tournament_id=tournament["id"])
        )
        
    series = None
    if match["series_id"]:
        series = db.execute(
            """
            SELECT s.*,
                   t1.name AS team1_name,
                   t2.name AS team2_name
            FROM series s
            LEFT JOIN teams t1 ON t1.id = s.team1_id
            LEFT JOIN teams t2 ON t2.id = s.team2_id
            WHERE s.id = ?
            """,
            (match["series_id"],)
        ).fetchone()

    if request.method == "POST":
        scheduled_at = request.form.get("scheduled_at")

        racetime_room_raw = request.form.get("racetime_room", "").strip()
        racetime_room = racetime_room_raw or None

        db.execute(
            """
            UPDATE matches
            SET scheduled_at = ?, racetime_room = ?
            WHERE id = ?
            """,
            (scheduled_at, racetime_room, match_id)
        )
        db.commit()

        flash(_("Match mis à jour."), "success")
        return redirect(
            url_for("admin.admin_matches", tournament_id=tournament["id"])
        )

    return render_template(
        "admin/matches/match_form.html",
        match=match,
        tournament=tournament,
        series=series,
        series_id=match["series_id"]
    )

@admin_bp.route(
    "/matches/confrontations/<int:series_id>/delete",
    methods=["POST"]
)
@login_required
@role_required("admin")
def admin_confrontation_delete(series_id):
    db = get_db()

    match_count = db.execute(
        "SELECT COUNT(*) FROM matches WHERE series_id = ?",
        (series_id,)
    ).fetchone()[0]

    if match_count > 0:
        flash(_("Impossible de supprimer une confrontation avec des matchs."), "error")
        return redirect(url_for("admin.admin_matches"))

    db.execute("DELETE FROM series WHERE id = ?", (series_id,))
    db.commit()

    flash(_("Confrontation supprimée."), "success")
    return redirect(url_for("admin.admin_matches"))

@admin_bp.route(
    "/matches/<int:match_id>/delete",
    methods=["POST"]
)
@login_required
@role_required("admin")
def admin_match_delete(match_id):
    db = get_db()

    match = db.execute(
        "SELECT * FROM matches WHERE id = ?",
        (match_id,)
    ).fetchone()

    if not match:
        flash(_("Match introuvable."), "error")
        return redirect(url_for("admin.admin_matches"))

    series_id = match["series_id"]
    was_completed = match["is_completed"]

    db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    db.commit()

    # 🔁 Recalcul du vainqueur si nécessaire
    if series_id and was_completed:
        from app.modules.results import update_series_result
        update_series_result(series_id)

    flash(_("Match supprimé."), "success")

    if series_id:
        return redirect(
            url_for("admin.admin_confrontation_matches", series_id=series_id)
        )

    return redirect(
        url_for("admin.admin_matches", tournament_id=match["tournament_id"])
    )



@admin_bp.route(
    "/matches/<int:match_id>/results",
    methods=["GET", "POST"]
)
@login_required
@role_required("admin")
def admin_match_results(match_id):
    db = get_db()

    # --- Match ---
    match = db.execute(
        """
        SELECT *
        FROM matches
        WHERE id = ?
        """,
        (match_id,)
    ).fetchone()

    if not match:
        flash(_("Match introuvable."), "error")
        return redirect(url_for("admin.admin_matches"))

    # --- Équipes du match ---
    teams = db.execute(
        """
        SELECT
            mt.team_id,
            t.name,
            mt.final_time_raw,
            mt.final_time,
            mt.position,
            mt.is_winner
        FROM match_teams mt
        JOIN teams t ON t.id = mt.team_id
        WHERE mt.match_id = ?
        ORDER BY mt.position ASC, t.name
        """,
        (match_id,)
    ).fetchall()

    if request.method == "POST":
        results = []
        errors = False

        from app.modules.results import parse_final_time, InvalidResultFormat

        # --- Parsing ---
        for t in teams:
            field_name = f"result_{t['team_id']}"
            raw_value = request.form.get(field_name, "").strip()

            try:
                final_time, status = parse_final_time(raw_value)
            except InvalidResultFormat as e:
                flash(f"{t['name']} : {str(e)}", "error")
                errors = True
                continue

            results.append({
                "team_id": t["team_id"],
                "final_time_raw": raw_value.upper(),
                "final_time": final_time,
                "status": status
            })

        if errors:
            return redirect(request.url)

        # --- Classement ---
        timed = [r for r in results if r["final_time"] is not None]
        others = [r for r in results if r["final_time"] is None]

        timed.sort(key=lambda r: r["final_time"])

        ordered = timed + others

        # Détection d'égalité pour la première place
        first_time = ordered[0]["final_time"]

        is_tie_for_first = (
            first_time is not None and
            sum(1 for r in ordered if r["final_time"] == first_time) > 1
        )
        
        # --- Mise à jour ---
        for idx, r in enumerate(ordered, start=1):
            is_winner = 1 if idx == 1 and not is_tie_for_first else 0


            db.execute(
                """
                UPDATE match_teams
                SET
                    final_time_raw = ?,
                    final_time = ?,
                    position = ?,
                    is_winner = ?
                WHERE match_id = ?
                  AND team_id = ?
                """,
                (
                    r["final_time_raw"],
                    r["final_time"],
                    idx,
                    is_winner,
                    match_id,
                    r["team_id"]
                )
            )

        db.execute(
            "UPDATE matches SET is_completed = 1 WHERE id = ?",
            (match_id,)
        )

        db.commit()
        
        if match["series_id"]:
            from app.modules.results import update_series_result
            update_series_result(match["series_id"])


        flash(_("Résultats enregistrés."), "success")
        if match["series_id"]:
            return redirect(
                url_for(
                    "admin.admin_confrontation_matches",
                    series_id=match["series_id"]
                )
            )
        else:
            return redirect(
                url_for(
                    "admin.admin_matches",
                    tournament_id=match["tournament_id"]
                )
            )

    return render_template(
        "admin/matches/match_results.html",
        match=match,
        teams=teams
    )

@admin_bp.route(
    "/matches/<int:match_id>/results/racetime/prefill",
    methods=["GET"]
)
@login_required
@role_required("admin")
def admin_match_results_racetime_prefill(match_id: int):
    try:
        db = get_db()

        # 1) Match + racetime_room
        match = db.execute(
            "SELECT id, racetime_room FROM matches WHERE id = ?",
            (match_id,)
        ).fetchone()

        if not match:
            return jsonify({"ok": False, "error": "Match introuvable."}), 404

        racetime_room = (match["racetime_room"] or "").strip()
        if not racetime_room:
            return jsonify({"ok": False, "error": "Aucune room racetime associée à ce match."}), 400

        # 2) Teams du match
        teams = db.execute(
            """
            SELECT mt.team_id
            FROM match_teams mt
            WHERE mt.match_id = ?
            """,
            (match_id,)
        ).fetchall()

        if not teams:
            return jsonify({"ok": False, "error": "Aucune équipe associée à ce match."}), 400

        team_ids = [t["team_id"] for t in teams]

        # 3) Récupérer TOUS les racetime_user de chaque team (co-op support)
        #    (team time = last finisher time, géré dans le module racetime)
        placeholders = ",".join(["?"] * len(team_ids))
        rows = db.execute(
            f"""
            SELECT
                tp.team_id,
                p.racetime_user
            FROM team_players tp
            JOIN players p ON p.id = tp.player_id
            WHERE tp.team_id IN ({placeholders})
            ORDER BY tp.team_id, tp.position ASC
            """,
            tuple(team_ids)
        ).fetchall()

        team_to_users: dict[int, list[str]] = {tid: [] for tid in team_ids}
        for r in rows:
            tid = r["team_id"]
            rt = (r["racetime_user"] or "").strip()
            if rt:
                team_to_users[tid].append(rt)

        # Si une team n'a aucun racetime_user, on refuse (plus clair pour le MVP)
        missing_team_ids = [tid for tid, users in team_to_users.items() if not users]
        if missing_team_ids:
            return jsonify({
                "ok": False,
                "error": "Certaines équipes n'ont pas de racetime_user renseigné (players).",
                "missing_team_ids": missing_team_ids
            }), 400

        # 4) Fetch racetime + build results payload
        try:
            race_json = racetime_mod.fetch_race_data(racetime_room)
            results, meta = racetime_mod.build_prefill_payload_for_teams(team_to_users, race_json)
        except racetime_mod.RacetimeRoomInvalid:
            return jsonify({"ok": False, "error": "URL racetime invalide."}), 400
        except racetime_mod.RacetimeFetchError:
            return jsonify({"ok": False, "error": "Impossible de contacter racetime ou réponse invalide."}), 502

        # Si on ne peut rien calculer pour certaines teams, on renvoie quand même (préfill partiel possible)
        return jsonify({
            "ok": True,
            "results": results,
            "meta": meta
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import current_user
from app.database import get_db
from app.auth.utils import login_required
from werkzeug.security import check_password_hash, generate_password_hash
import json
import math
from app.modules.tournaments import ensure_public_tournament

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    return render_template("main/index.html")


@main_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    db = get_db()

    if request.method == "POST":
        description = request.form.get("description", "").strip()

        links = {
            "racetime": request.form.get("link_racetime", "").strip(),
            "twitch": request.form.get("link_twitch", "").strip(),
            "youtube": request.form.get("link_youtube", "").strip(),
            "discord": request.form.get("discord_handle", "").strip(),
        }

        links = {k: v for k, v in links.items() if v}
        links_json = json.dumps(links)

        db.execute(
            """
            UPDATE users
            SET description = ?, social_links = ?
            WHERE id = ?
            """,
            (description, links_json, current_user.id)
        )
        db.commit()

        flash("Profil mis à jour !", "success")
        return redirect(url_for("main.profile"))

    user = db.execute(
        """
        SELECT username, role, created_at, last_login,
               avatar_filename, description, social_links
        FROM users WHERE id = ?
        """,
        (current_user.id,)
    ).fetchone()

    links = json.loads(user["social_links"]) if user["social_links"] else {}

    return render_template("main/profile.html", user=dict(user), links=links, user_id=current_user.id)


@main_bp.route("/profile/password", methods=["GET", "POST"])
@login_required
def change_password():
    db = get_db()

    if request.method == "POST":
        old_password = request.form.get("old_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        row = db.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (current_user.id,)
        ).fetchone()

        errors = []
        if not row:
            abort(403)

        if not check_password_hash(row["password_hash"], old_password):
            errors.append("L'ancien mot de passe est incorrect.")

        if len(new_password) < 6:
            errors.append("Le nouveau mot de passe doit faire au moins 6 caractères.")

        if new_password != confirm_password:
            errors.append("La confirmation ne correspond pas.")

        if errors:
            return render_template(
                "main/change_password.html",
                errors=errors
            )


        new_hash = generate_password_hash(new_password)

        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_hash, current_user.id)
        )
        db.commit()

        flash("Mot de passe mis à jour avec succès !", "success")
        return redirect(url_for("main.profile"))

    return render_template("main/change_password.html")


@main_bp.route("/user/<int:user_id>")
def public_profile(user_id):
    db = get_db()
    user = db.execute(
        """
        SELECT username, role, created_at,
               avatar_filename, description, social_links
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()

    if not user:
        flash("Utilisateur introuvable.", "error")
        return redirect(url_for("main.home"))

    links = json.loads(user["social_links"]) if user["social_links"] else {}

    return render_template("main/public_profile.html", user=dict(user), links=links)


@main_bp.route("/u/<username>")
def public_profile_by_name(username):
    db = get_db()
    user = db.execute(
        "SELECT id FROM users WHERE username = ?",
        (username,)
    ).fetchone()

    if not user:
        flash("Utilisateur introuvable.", "error")
        return redirect(url_for("main.home"))

    return redirect(url_for("main.public_profile", user_id=user["id"]))




@main_bp.route("/tournament/<slug>")
def tournament(slug):
    db = get_db()

    # -------------------------------------------------
    # Tournoi interne (BDD)
    # -------------------------------------------------
    tournament = db.execute(
        """
        SELECT
            t.id,
            t.name,
            t.slug,
            t.status,
            t.metadata,
            t.created_at,
            g.name AS game_name
        FROM tournaments t
        LEFT JOIN games g ON g.id = t.game_id
        WHERE t.slug = ?
          AND t.source = 'internal'
        """,
        (slug,)
    ).fetchone()

    if tournament:
        ensure_public_tournament(tournament)
        # -----------------------------
        # Statut PUBLIC (mapping v1)
        # -----------------------------
        public_status = tournament["status"]

        if public_status == "draft":
            public_status = "upcoming"

        # -----------------------------
        # Metadata (JSON)
        # -----------------------------
        metadata = {}

        if tournament["metadata"]:
            try:
                metadata = json.loads(tournament["metadata"])
            except ValueError:
                metadata = {}

        # Fallbacks v1
        metadata.setdefault("edition", None)
        metadata.setdefault("description", None)
        metadata.setdefault("organizers", [])
        metadata.setdefault("highlights", [])
        metadata.setdefault("external_links", {})

        # -----------------------------
        # Équipes participantes
        # -----------------------------
        teams = db.execute(
            """
            SELECT DISTINCT tm.id, tm.name
            FROM teams tm
            JOIN match_teams mt ON mt.team_id = tm.id
            JOIN matches m ON m.id = mt.match_id
            WHERE m.tournament_id = ?
            ORDER BY tm.name ASC
            """,
            (tournament["id"],)
        ).fetchall()

        return render_template(
            "tournaments/internal.html",
            tournament=tournament,
            metadata=metadata,
            teams=teams,
            public_status=public_status
        )

    # -------------------------------------------------
    # Fallback tournoi externe (archives)
    # -------------------------------------------------
    tournaments_external = current_app.config.get("TOURNAMENTS", [])

    external = next(
        (t for t in tournaments_external if t.get("slug") == slug),
        None
    )

    if external:
        return render_template(
            "tournaments/external.html",
            tournament=external
        )

    abort(404)



import json
from flask import render_template, abort
from app.database import get_db

@main_bp.route("/tournament/<slug>/results")
def tournament_results(slug):
    db = get_db()

    # -------------------------------------------------
    # Tournoi
    # -------------------------------------------------
    tournament = db.execute(
        """
        SELECT
            t.id,
            t.name,
            t.slug,
            t.status,
            t.metadata,
            g.name AS game_name
        FROM tournaments t
        LEFT JOIN games g ON g.id = t.game_id
        WHERE t.slug = ?
          AND t.source = 'internal'
        """,
        (slug,)
    ).fetchone()

    if not tournament:
        abort(404)
        
    ensure_public_tournament(tournament)

    # -------------------------------------------------
    # Metadata JSON
    # -------------------------------------------------
    metadata = {}
    if tournament["metadata"]:
        try:
            metadata = json.loads(tournament["metadata"])
        except ValueError:
            metadata = {}

    metadata.setdefault("edition", None)

    # -------------------------------------------------
    # Phases
    # -------------------------------------------------
    phases = db.execute(
        """
        SELECT id, name, position
        FROM tournament_phases
        WHERE tournament_id = ?
        ORDER BY position ASC
        """,
        (tournament["id"],)
    ).fetchall()

    phase_ids = [p["id"] for p in phases]

    # -------------------------------------------------
    # Séries
    # -------------------------------------------------
    series_rows = []
    if phase_ids:
        placeholders = ",".join("?" for _ in phase_ids)
        series_rows = db.execute(
            f"""
            SELECT
                s.id,
                s.phase_id,
                s.stage,
                s.team1_id,
                s.team2_id,
                tw.name AS winner_name
            FROM series s
            LEFT JOIN teams tw ON tw.id = s.winner_team_id
            WHERE s.phase_id IN ({placeholders})
            ORDER BY s.id ASC
            """,
            phase_ids
        ).fetchall()

    series_ids = [s["id"] for s in series_rows]

    # -------------------------------------------------
    # Équipes par série
    # -------------------------------------------------
    teams_by_series = {}

    if series_ids:
        placeholders = ",".join("?" for _ in series_ids)
        rows = db.execute(
            f"""
            SELECT DISTINCT
                m.series_id,
                tm.name AS team_name
            FROM matches m
            JOIN match_teams mt ON mt.match_id = m.id
            JOIN teams tm ON tm.id = mt.team_id
            WHERE m.series_id IN ({placeholders})
            ORDER BY tm.name ASC
            """,
            series_ids
        ).fetchall()

        for r in rows:
            teams_by_series.setdefault(r["series_id"], []).append(r["team_name"])

    # -------------------------------------------------
    # Score BO (LOGIQUE ADMIN — is_winner)
    # -------------------------------------------------
    scores_by_series = {}

    if series_ids:
        placeholders = ",".join("?" for _ in series_ids)
        rows = db.execute(
            f"""
            SELECT
                s.id AS series_id,

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
            LEFT JOIN matches m
                ON m.series_id = s.id
                AND m.is_completed = 1
            LEFT JOIN match_teams mt
                ON mt.match_id = m.id
            WHERE s.id IN ({placeholders})
            GROUP BY s.id
            """,
            series_ids
        ).fetchall()

        for r in rows:
            if r["team1_wins"] or r["team2_wins"]:
                scores_by_series[r["series_id"]] = (
                    f"{r['team1_wins']}-{r['team2_wins']}"
                )

    # -------------------------------------------------
    # Assemblage par phase
    # -------------------------------------------------
    series_by_phase = {p["id"]: [] for p in phases}

    for s in series_rows:
        series_by_phase[s["phase_id"]].append({
            "stage": s["stage"],
            "teams": teams_by_series.get(s["id"], []),
            "winner_name": s["winner_name"],
            "score": scores_by_series.get(s["id"])
        })

    # -------------------------------------------------
    # Tie-breaks (matchs sans série)
    # -------------------------------------------------
    tiebreaks = []

    tb_matches = db.execute(
        """
        SELECT id, is_completed
        FROM matches
        WHERE tournament_id = ?
          AND series_id IS NULL
        ORDER BY id ASC
        """,
        (tournament["id"],)
    ).fetchall()

    tb_ids = [m["id"] for m in tb_matches]

    teams_by_match = {}
    if tb_ids:
        placeholders = ",".join("?" for _ in tb_ids)
        rows = db.execute(
            f"""
            SELECT
                mt.match_id,
                tm.name AS team_name
            FROM match_teams mt
            JOIN teams tm ON tm.id = mt.team_id
            WHERE mt.match_id IN ({placeholders})
            ORDER BY mt.team_id ASC
            """,
            tb_ids
        ).fetchall()

        for r in rows:
            teams_by_match.setdefault(r["match_id"], []).append(r["team_name"])

    for m in tb_matches:
        tiebreaks.append({
            "teams": teams_by_match.get(m["id"], []),
            "positions": None,   # prévu plus tard
            "is_completed": m["is_completed"]
        })

    return render_template(
        "tournaments/results.html",
        tournament=tournament,
        metadata=metadata,
        phases=phases,
        series_by_phase=series_by_phase,
        tiebreaks=tiebreaks
    )




import json
from flask import render_template, abort
from app.database import get_db

@main_bp.route("/tournament/<slug>/bracket")
def tournament_bracket(slug):
    db = get_db()

    # -------------------------------------------------
    # Tournoi
    # -------------------------------------------------
    tournament = db.execute(
        """
        SELECT
            t.id,
            t.name,
            t.slug,
            t.status,
            t.metadata,
            g.name AS game_name
        FROM tournaments t
        LEFT JOIN games g ON g.id = t.game_id
        WHERE t.slug = ?
          AND t.source = 'internal'
        """,
        (slug,)
    ).fetchone()

    if not tournament:
        abort(404)

    ensure_public_tournament(tournament)

    # -------------------------------------------------
    # Metadata
    # -------------------------------------------------
    metadata = {}
    if tournament["metadata"]:
        try:
            metadata = json.loads(tournament["metadata"])
        except ValueError:
            metadata = {}

    # -------------------------------------------------
    # Phases du tournoi (ordre officiel)
    # -------------------------------------------------
    phases_rows = db.execute(
        """
        SELECT
            id,
            name,
            type,
            position,
            details
        FROM tournament_phases
        WHERE tournament_id = ?
        ORDER BY position ASC
        """,
        (tournament["id"],)
    ).fetchall()

    processed_phases = []

    # -------------------------------------------------
    # Boucle sur les phases
    # -------------------------------------------------
    for phase_row in phases_rows:
        phase = dict(phase_row)
        ptype = (phase["type"] or "").strip().lower()

        if ptype == "groups":
            display_type = "groups"
        elif ptype == "bracket_simple_elim":
            display_type = "bracket_simple_elim"
        else:
            display_type = "default"

        # =============================
        # PHASE DE GROUPES
        # =============================
        if display_type == "groups":

            teams_rows = db.execute(
                """
                SELECT
                    tt.team_id,
                    tm.name AS team_name,
                    tt.group_name,
                    tt.seed,
                    tt.position
                FROM tournament_teams tt
                JOIN teams tm ON tm.id = tt.team_id
                WHERE tt.tournament_id = ?
                  AND tt.group_name IS NOT NULL
                  AND TRIM(tt.group_name) != ''
                ORDER BY tt.group_name COLLATE NOCASE, tm.name COLLATE NOCASE
                """,
                (tournament["id"],)
            ).fetchall()

            wins_rows = db.execute(
                """
                SELECT
                    winner_team_id AS team_id,
                    COUNT(*) AS wins
                FROM series
                WHERE phase_id = ?
                  AND winner_team_id IS NOT NULL
                GROUP BY winner_team_id
                """,
                (phase["id"],)
            ).fetchall()

            wins_by_team = {r["team_id"]: r["wins"] for r in wins_rows}

            played_rows = db.execute(
                """
                SELECT
                    x.team_id,
                    COUNT(*) AS played
                FROM (
                    SELECT team1_id AS team_id
                    FROM series
                    WHERE phase_id = ?
                      AND team1_id IS NOT NULL
                      AND team2_id IS NOT NULL
                    UNION ALL
                    SELECT team2_id AS team_id
                    FROM series
                    WHERE phase_id = ?
                      AND team1_id IS NOT NULL
                      AND team2_id IS NOT NULL
                ) x
                GROUP BY x.team_id
                """,
                (phase["id"], phase["id"])
            ).fetchall()

            played_by_team = {r["team_id"]: r["played"] for r in played_rows}

            groups_map = {}
            for r in teams_rows:
                gname = r["group_name"]
                team_id = r["team_id"]
                wins = int(wins_by_team.get(team_id, 0))
                played = int(played_by_team.get(team_id, 0))

                groups_map.setdefault(gname, []).append({
                    "team_id": team_id,
                    "team": r["team_name"],
                    "wins": wins,
                    "played": played,
                    "losses": max(0, played - wins),
                    "seed": r["seed"],
                    "position": r["position"],
                })

            groups = []
            for gname, rows in groups_map.items():
                rows_sorted = sorted(
                    rows,
                    key=lambda x: (
                        -x["wins"],
                        x["position"] is None,
                        x["position"] if x["position"] is not None else 10**9,
                        x["seed"] if x["seed"] is not None else 10**9,
                        x["team"].lower(),
                    )
                )
                groups.append({
                    "id": phase["id"],
                    "name": gname,
                    "standings": rows_sorted,
                })

            groups.sort(key=lambda g: g["name"].lower())

            qualifiers_per_group = None
            try:
                if phase.get("details"):
                    details = json.loads(phase["details"])
                    q = details.get("qualifiers_per_group")
                    if q is not None:
                        qualifiers_per_group = int(q)
            except Exception:
                qualifiers_per_group = None

            processed_phases.append({
                "id": phase["id"],
                "name": phase["name"],
                "display_type": "groups",
                "data": {
                    "groups": groups,
                    "qualifiers_per_group": qualifiers_per_group,
                },
            })

        # =============================
        # PHASE DE BRACKET (simple élimination)
        # =============================
        elif display_type == "bracket_simple_elim":

            series_rows = db.execute(
                """
                SELECT
                    s.id,
                    s.round,
                    s.stage,
                    s.best_of,
                    s.team1_id,
                    s.team2_id,
                    t1.name AS team1_name,
                    t2.name AS team2_name,
                    s.source_team1_series_id,
                    s.source_team1_type,
                    s.source_team2_series_id,
                    s.source_team2_type,
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
                LEFT JOIN teams t1 ON t1.id = s.team1_id
                LEFT JOIN teams t2 ON t2.id = s.team2_id
                LEFT JOIN matches m
                    ON m.series_id = s.id
                    AND m.is_completed = 1
                LEFT JOIN match_teams mt
                    ON mt.match_id = m.id
                WHERE s.phase_id = ?
                GROUP BY s.id
                ORDER BY s.round ASC, s.stage ASC
                """,
                (phase["id"],)
            ).fetchall()

            source_label_by_id = {
                str(r["id"]): (r["stage"] or f"Série #{r['id']}")
                for r in series_rows
            }


            from collections import defaultdict

            rounds_map = defaultdict(list)
            series_by_id = {}

            def _safe_int(x):
                try:
                    return int(x)
                except Exception:
                    return None

            # 1) Construire tous les objets "série" (modifiables)
            for row in series_rows:
                src1 = row["source_team1_series_id"]
                src2 = row["source_team2_series_id"]

                s_obj = {
                    "id": str(row["id"]),
                    "round": row["round"],
                    "stage": row["stage"],   # on garde l’original
                    "label": row["stage"],
                    "team1": {
                        "id": row["team1_id"],
                        "name": row["team1_name"] or "À déterminer",
                        "wins": row["team1_wins"] or 0,
                        "source_series_id": str(src1) if src1 is not None else None,
                        "source_type": row["source_team1_type"],
                        "source_label": source_label_by_id.get(str(src1)) if src1 is not None else None,
                    },
                    "team2": {
                        "id": row["team2_id"],
                        "name": row["team2_name"] or "À déterminer",
                        "wins": row["team2_wins"] or 0,
                        "source_series_id": str(src2) if src2 is not None else None,
                        "source_type": row["source_team2_type"],
                        "source_label": source_label_by_id.get(str(src2)) if src2 is not None else None,
                    },
                    "best_of": row["best_of"],
                    # marqueurs utiles pour le template (ne casse rien si ignoré)
                    "is_virtual": False,
                    "is_bye": False,
                }

                series_by_id[s_obj["id"]] = s_obj


            # 2) Injection des "séries virtuelles Bye" (uniquement affichage)
            # On fait ça avant de remplir rounds_map pour pouvoir insérer dans le round précédent.
            min_round = min((s["round"] for s in series_by_id.values()), default=1)

            def make_bye_series(parent_series, side_key):
                """
                parent_series: la série du round r (r>min_round) où une équipe est seedée sans source
                side_key: "team1" ou "team2" (côté où l’équipe arrive via bye)
                """
                parent_id = parent_series["id"]
                r = parent_series["round"]
                if r <= min_round:
                    return None  # pas de bye à injecter au 1er round

                team = parent_series[side_key]
                if team["id"] is None:
                    return None  # pas d’équipe réelle => pas un bye, juste "à déterminer"
                if team["source_series_id"] is not None:
                    return None  # il y a déjà une source => pas un bye

                # Déduire une "stage" cohérente dans le round précédent si stage est numérique
                parent_stage_int = _safe_int(parent_series["stage"])
                prev_round = r - 1

                # convention bracket classique : feeders de stage S = (2S-1, 2S)
                if parent_stage_int is not None:
                    prev_stage_int = (2 * parent_stage_int - 1) if side_key == "team1" else (2 * parent_stage_int)
                    prev_stage = str(prev_stage_int)
                else:
                    prev_stage = "BYE"

                virtual_id = f"vbye:{parent_id}:{side_key}"

                v = {
                    "id": virtual_id,
                    "round": prev_round,
                    "stage": prev_stage,
                    "label": "Bye",
                    "team1": {
                        "id": team["id"],
                        "name": team["name"],
                        "wins": 1,
                        "source_series_id": None,
                        "source_type": None,
                        "source_label": None,
                    },
                    "team2": {
                        "id": None,
                        "name": "Bye",
                        "wins": 0,
                        "source_series_id": None,
                        "source_type": None,
                        "source_label": None,
                    },
                    "best_of": 1,
                    "is_virtual": True,
                    "is_bye": True,
                    # optionnel si un jour tu veux afficher un badge "qualifié"
                    "winner_team_id": team["id"],
                }

                # Important : mettre la "source" côté parent pour que l’affichage soit cohérent
                team["source_series_id"] = virtual_id
                team["source_type"] = "winner"
                team["source_label"] = "Bye"

                # Et permettre au label mapping de retrouver cet id si ton template l’utilise
                source_label_by_id[virtual_id] = "Bye"

                return v


            virtual_series = []
            for s in list(series_by_id.values()):
                v1 = make_bye_series(s, "team1")
                if v1:
                    virtual_series.append(v1)
                v2 = make_bye_series(s, "team2")
                if v2:
                    virtual_series.append(v2)

            # 3) Remplir rounds_map avec vraies + virtuelles séries
            for s in series_by_id.values():
                rounds_map[s["round"]].append(s)

            for v in virtual_series:
                rounds_map[v["round"]].append(v)

            # 4) Tri stable dans chaque round (stage ASC si possible)
            def stage_sort_key(s):
                si = _safe_int(s.get("stage"))
                return (0, si) if si is not None else (1, str(s.get("stage") or ""))

            for r in rounds_map:
                rounds_map[r].sort(key=stage_sort_key)


            processed_phases.append({
                "id": phase["id"],
                "name": phase["name"],
                "display_type": "bracket_simple_elim",
                "data": {
                    "bracket": {
                        "rounds": [
                            {
                                "round": r,
                                "series": rounds_map[r],
                            }
                            for r in sorted(rounds_map.keys())
                        ]
                    }
                },
            })

    return render_template(
        "tournaments/bracket.html",
        tournament=tournament,
        metadata=metadata,
        phases=processed_phases,
    )

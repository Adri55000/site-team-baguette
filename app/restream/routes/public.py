from flask import render_template, abort, request
from flask_login import current_user
from flask_babel import get_locale as babel_get_locale, gettext as _

from .. import restream_bp

from app.database import get_db
from app.permissions.roles import has_required_role
from app.modules.i18n import get_translation


@restream_bp.route("/")
def index():
    return render_template("restream/index.html")

@restream_bp.route("/<slug>")
def view(slug):
    db = get_db()
    restream = db.execute(
        """
        SELECT r.title, r.slug, r.twitch_url, r.created_at, r.restreamer_name, r.commentator_name, r.tracker_name, r.indices_template, r.tracker_type,
               u.username AS creator
        FROM restreams r
        JOIN users u ON u.id = r.created_by
        WHERE r.slug = ? AND r.is_active = 1
        """,
        (slug,)
    ).fetchone()

    if not restream:
        abort(404)
        
    can_edit = current_user.is_authenticated and has_required_role(
        getattr(current_user, "role", None),
        "éditeur",
    )

    return render_template(
        "restream/view.html",
        restream=restream,
        can_edit=can_edit
    )

@restream_bp.route("/planning")
def planning():
    db = get_db()

    # -------------------------------------------------
    # Paramètres GET (pattern admin)
    # -------------------------------------------------
    page = request.args.get("page", 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    tournament_id = request.args.get("tournament", type=int)
    show_past = request.args.get("show_past")
    
    filter_kind = request.args.get("filter", type=str)
    restream_only = (filter_kind == "restream")

    # -------------------------------------------------
    # Filtres SQL communs
    # -------------------------------------------------
    where = ["m.scheduled_at IS NOT NULL"]
    params = []

    if tournament_id:
        where.append("m.tournament_id = ?")
        params.append(tournament_id)

    if not show_past:
        where.append("m.scheduled_at >= datetime('now')")
        
    if restream_only:
        where.append("""
            EXISTS (
                SELECT 1
                FROM restreams r2
                WHERE r2.match_id = m.id
                  AND r2.is_active = 1
            )
        """)

    where_sql = " AND ".join(where)

    # -------------------------------------------------
    # TOTAL (pagination)
    # -------------------------------------------------
    total = db.execute(
        f"""
        SELECT COUNT(*)
        FROM matches m
        WHERE {where_sql}
        """,
        params
    ).fetchone()[0]

    total_pages = max(1, (total + per_page - 1) // per_page)

    # -------------------------------------------------
    # IDs des matchs paginés (clé de pagination)
    # -------------------------------------------------
    match_ids = db.execute(
        f"""
        SELECT m.id
        FROM matches m
        WHERE {where_sql}
        ORDER BY m.scheduled_at ASC
        LIMIT ? OFFSET ?
        """,
        (*params, per_page, offset)
    ).fetchall()

    match_ids = [row["id"] for row in match_ids]

    if not match_ids:
        matches = []
    else:
        placeholders = ",".join("?" for _ in match_ids)

        # -------------------------------------------------
        # Données complètes des matchs
        # -------------------------------------------------
        rows = db.execute(
            f"""
            SELECT
                m.id AS match_id,
                m.scheduled_at,
                m.is_completed,
                m.series_id,

                t.id AS tournament_id,
                t.slug AS tournament_slug,
                t.name AS tournament_name,

                s.stage AS series_stage,
                p.id AS phase_id,
                p.name AS phase_name,

                r.slug AS restream_slug,
                r.title AS restream_title,

                tm.name AS team_name

            FROM matches m

            JOIN tournaments t
                ON t.id = m.tournament_id

            LEFT JOIN series s
                ON s.id = m.series_id

            LEFT JOIN tournament_phases p
                ON p.id = s.phase_id

            LEFT JOIN match_teams mt
                ON mt.match_id = m.id

            LEFT JOIN teams tm
                ON tm.id = mt.team_id

            LEFT JOIN restreams r
                ON r.match_id = m.id
               AND r.is_active = 1

            WHERE m.id IN ({placeholders})

            ORDER BY m.scheduled_at ASC
            """,
            match_ids
        ).fetchall()

        # -------------------------------------------------
        # Regroupement par match
        # -------------------------------------------------
        matches_map = {}

        for row in rows:
            match_id = row["match_id"]

            if match_id not in matches_map:
                matches_map[match_id] = {
                "match_id": match_id,
                "scheduled_at": row["scheduled_at"],
                "is_completed": row["is_completed"],
                "series_id": row["series_id"],

                "tournament_id": row["tournament_id"],
                "tournament_slug": row["tournament_slug"],
                "tournament_name": row["tournament_name"],

                "phase_id": row["phase_id"],
                "phase_name": row["phase_name"],

                "stage_label": row["series_stage"] or _("Tie-break"),

                "restream_slug": row["restream_slug"],
                "restream_title": row["restream_title"],

                "teams": [],
                "game_number": None,
            }

            if row["team_name"]:
                matches_map[match_id]["teams"].append(row["team_name"])

        # -------------------------------------------------
        # Numérotation des games (par série, chronologique)
        # -------------------------------------------------
        from collections import defaultdict

        series_groups = defaultdict(list)

        for match in matches_map.values():
            if match["series_id"] is not None:
                series_groups[match["series_id"]].append(match)

        for series_id, series_matches in series_groups.items():
            series_matches.sort(key=lambda m: m["scheduled_at"])

            for index, match in enumerate(series_matches, start=1):
                match["game_number"] = index

        # -------------------------------------------------
        # Respect de l'ordre paginé
        # -------------------------------------------------
        matches = [matches_map[mid] for mid in match_ids if mid in matches_map]
        
        # -------------------------------------------------
        # Traductions affichage (tournoi + phase)
        # -------------------------------------------------
        lang = str(babel_get_locale() or "fr").strip().lower()

        for m in matches:
            # tournoi
            tslug = m.get("tournament_slug")
            if tslug:
                t_tr = get_translation("tournament", tslug, "name", lang)
                if t_tr:
                    m["tournament_name"] = t_tr

            # phase (si présente)
            pid = m.get("phase_id")
            if pid is not None:
                p_tr = get_translation("tournament_phase", str(pid), "name", lang)
                if p_tr:
                    m["phase_name"] = p_tr

    # -------------------------------------------------
    # Liste des tournois (filtre)
    # -------------------------------------------------
    tournaments = db.execute(
        """
        SELECT id, slug, name
        FROM tournaments
        ORDER BY created_at DESC
        """
    ).fetchall()

    lang = str(babel_get_locale() or "fr").strip().lower()

    tournaments = [dict(t) for t in tournaments]
    for t in tournaments:
        tr = get_translation("tournament", t["slug"], "name", lang) if t.get("slug") else None
        t["display_name"] = tr if tr else t.get("name")


    return render_template(
        "restream/planning.html",
        matches=matches,
        tournaments=tournaments,
        page=page,
        total_pages=total_pages,
        filter_kind=filter_kind,
        restream_only=restream_only,
        tournament_id=tournament_id,
        show_past=show_past,
    )
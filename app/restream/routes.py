import json
from pathlib import Path
from flask import (
    Blueprint, render_template, abort,
    request, redirect, url_for, Response, flash, current_app, jsonify, stream_with_context
)
import time
from flask_login import current_user
from app.database import get_db
from shutil import copyfile
import re
from datetime import datetime

from app.auth.utils import login_required
from app.permissions.decorators import role_required
from app.permissions.roles import has_required_role
from app.modules.text import slugify
from app.modules.tracker.base import ensure_session_restream, save_session_restream, load_session_restream
from app.modules.indices.registry import get_available_indices_templates, is_valid_indices_template, get_indices_template_path
from app.modules.tracker.registry import get_available_trackers, get_tracker_definition, is_valid_tracker_type
from app.modules.tracker.presets import list_presets, load_preset
from app.restream.queries import get_active_restream_by_slug, get_match_teams, get_next_planned_match_for_overlay, simplify_restream_title, split_commentators
from app.modules.overlay.registry import resolve_overlay_pack_for_match
from app.modules.tournaments import overlay_tournament_name
from app.modules.racetime import fetch_race_data, extract_entrants_overlay_info

# === Dossiers ===

def indices_sessions_dir() -> Path:
    return Path(current_app.instance_path) / "indices" / "sessions"

def indices_templates_dir() -> Path:
    return Path(current_app.instance_path) / "indices" / "templates"
    
def tracker_session_path_restream(restream_id: int) -> Path:
    return Path(current_app.instance_path) / "trackers" / "sessions" / f"restream_{restream_id}.json"

SSE_POLL_INTERVAL = 0.25


restream_bp = Blueprint("restream", __name__, url_prefix="/restream")

@restream_bp.route("/")
def index():
    return render_template("restream/index.html")

@restream_bp.route("/<slug>")
def view(slug):
    db = get_db()
    restream = db.execute(
        """
        SELECT r.title, r.slug, r.twitch_url, r.created_at, r.restreamer_name, r.commentator_name, r.indices_template, r.tracker_type,
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
                t.name AS tournament_name,

                s.stage AS series_stage,
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
                    "tournament_id": row["tournament_id"],
                    "tournament_name": row["tournament_name"],
                    "series_id": row["series_id"],
                    "stage_label": row["series_stage"] or "Tie-break",
                    "phase_name": row["phase_name"],
                    "restream_slug": row["restream_slug"],
                    "restream_title": row["restream_title"],
                    "teams": [],
                    "game_number": None,  # rempli plus bas
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
    # Liste des tournois (filtre)
    # -------------------------------------------------
    tournaments = db.execute(
        """
        SELECT id, name
        FROM tournaments
        ORDER BY created_at DESC
        """
    ).fetchall()

    return render_template(
        "restream/planning.html",
        matches=matches,
        tournaments=tournaments,
        page=page,
        total_pages=total_pages
    )



@restream_bp.route("/manage")
@role_required("restreamer")
def manage():
    db = get_db()

    rows = db.execute(
        """
        SELECT
            r.id,
            r.slug,
            r.title,
            r.created_at,
            r.is_active,

            m.scheduled_at,
            m.is_completed,

            t.name AS tournament_name,

            GROUP_CONCAT(
                CASE
                    WHEN te.name LIKE 'Solo - %'
                        THEN SUBSTR(te.name, 8)
                    ELSE te.name
                END,
                ' vs '
            ) AS teams_display

        FROM restreams r

        JOIN matches m
            ON m.id = r.match_id

        JOIN tournaments t
            ON t.id = m.tournament_id

        JOIN match_teams mt
            ON mt.match_id = m.id

        JOIN teams te
            ON te.id = mt.team_id

        GROUP BY r.id
        ORDER BY m.scheduled_at ASC
        """
    ).fetchall()

    now = datetime.utcnow()
    restreams = []

    for r in rows:
        scheduled_dt = None
        if r["scheduled_at"]:
            try:
                scheduled_dt = datetime.fromisoformat(r["scheduled_at"])
            except ValueError:
                scheduled_dt = None

        if not r["is_active"]:
            status = "inactive"
        elif scheduled_dt and scheduled_dt < now:
            status = "past"
        else:
            status = "upcoming"

        restreams.append({
            **dict(r),
            "status": status,
            "is_active": bool(r["is_active"]),
        })


    return render_template(
        "restream/manage.html",
        restreams_manage=restreams
    )



@restream_bp.route("/create", methods=["GET", "POST"])
@login_required
@role_required("restreamer")
def create():
    db = get_db()

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------
    if request.method == "POST":
        title = request.form.get("title")
        match_id = request.form.get("match_id")
        indices_template = request.form.get("indices_template")
        tracker_type = request.form.get("tracker_type")

        twitch_url = request.form.get("twitch_url") or None
        restreamer_name = request.form.get("restreamer_name") or None
        commentator_name = request.form.get("commentator_name") or None
        tracker_name = request.form.get("tracker_name") or None

        if not title or not match_id or not indices_template or not tracker_type:
            flash("Tous les champs obligatoires doivent être remplis.", "error")
            return redirect(url_for("restream.create"))

        # Vérification métier : match valide et sans restream
        match = db.execute(
            """
            SELECT m.id
            FROM matches m
            LEFT JOIN restreams r ON r.match_id = m.id
            WHERE m.id = ?
              AND m.is_completed = 0
              AND m.scheduled_at IS NOT NULL
              AND m.scheduled_at >= CURRENT_TIMESTAMP
              AND r.id IS NULL
            """,
            (match_id,),
        ).fetchone()

        if not match:
            flash("Match invalide ou déjà associé à un restream.", "error")
            return redirect(url_for("restream.create"))

        if not is_valid_indices_template(indices_template):
            flash("Template d’indices invalide.", "error")
            return redirect(url_for("restream.create"))

        if not is_valid_tracker_type(tracker_type):
            flash("Tracker invalide.", "error")
            return redirect(url_for("restream.create"))

        slug = slugify(title)

        # --------------------------------------------------------------
        # Indices : création de la session uniquement si != "none"
        # --------------------------------------------------------------
        if indices_template != "none":
            sessions_dir = Path(current_app.instance_path) / "indices" / "sessions"
            sessions_dir.mkdir(parents=True, exist_ok=True)
            session_path = sessions_dir / f"{slug}.json"

            template_path = get_indices_template_path(indices_template)
            copyfile(template_path, session_path)

        # --------------------------------------------------------------
        # Insert DB
        # --------------------------------------------------------------
        db.execute(
            """
            INSERT INTO restreams
                (
                    slug,
                    title,
                    created_by,
                    match_id,
                    indices_template,
                    tracker_type,
                    twitch_url,
                    restreamer_name,
                    commentator_name,
                    tracker_name
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slug,
                title,
                current_user.id,
                match_id,
                indices_template,
                tracker_type,
                twitch_url,
                restreamer_name,
                commentator_name,
                tracker_name,
            ),
        )
        db.commit()

        flash("Restream créé avec succès.", "success")
        return redirect(url_for("restream.manage"))

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    matches = db.execute(
        """
        SELECT
            m.id,
            m.scheduled_at,
            t.name AS tournament_name,
            GROUP_CONCAT(
                CASE
                    WHEN te.name LIKE 'Solo - %'
                        THEN SUBSTR(te.name, 8)
                    ELSE te.name
                END,
                ' vs '
            ) AS teams_display
        FROM matches m
        JOIN tournaments t ON t.id = m.tournament_id
        JOIN match_teams mt ON mt.match_id = m.id
        JOIN teams te ON te.id = mt.team_id
        LEFT JOIN restreams r ON r.match_id = m.id
        WHERE
            m.is_completed = 0
            AND m.scheduled_at IS NOT NULL
            AND m.scheduled_at >= CURRENT_TIMESTAMP
            AND r.id IS NULL
        GROUP BY m.id
        ORDER BY m.scheduled_at ASC
        """
    ).fetchall()

    return render_template(
        "restream/create.html",
        matches=matches,
        available_indices_templates=get_available_indices_templates(),
        available_tracker_types=get_available_trackers(),
    )


@restream_bp.route("/<slug>/enable", methods=["POST"])
@login_required
@role_required("restreamer")
def enable_restream(slug):
    db = get_db()

    updated = db.execute(
        """
        UPDATE restreams
        SET is_active = 1
        WHERE slug = ? AND is_active = 0
        """,
        (slug,)
    ).rowcount

    if not updated:
        abort(404)
        
    db.commit()
    
    # Recréation du fichier d’indices à partir du template
    restream = db.execute(
        "SELECT indices_template FROM restreams WHERE slug = ?",
        (slug,)
    ).fetchone()

    if not restream:
        abort(404)

    if restream["indices_template"] != "none":
        template_path = get_indices_template_path(restream["indices_template"])        
        session_path = indices_sessions_dir() / f"{slug}.json"
        session_path.parent.mkdir(parents=True, exist_ok=True)
        copyfile(template_path, session_path)


    flash("Restream réactivé.", "success")
    return redirect(url_for("restream.manage"))



@restream_bp.route("/<slug>/disable", methods=["POST"])
@login_required
@role_required("restreamer")
def disable_restream(slug):
    db = get_db()

    updated = db.execute(
        """
        UPDATE restreams
        SET is_active = 0
        WHERE slug = ? AND is_active = 1
        """,
        (slug,)
    ).rowcount

    if not updated:
        abort(404)
        
    db.commit()
    
    # Suppression du fichier d’indices si présent
    session_file = indices_sessions_dir() / f"{slug}.json"
    if session_file.exists():
        session_file.unlink()


    flash("Restream désactivé.", "success")
    return redirect(url_for("restream.manage"))



# =========================================================
# PAGE INDICES D’UN RESTREAM (LECTURE)
# =========================================================

@restream_bp.route("/<slug>/indices")
def restream_indices(slug):
    db = get_db()

    restream = db.execute(
        """
        SELECT title, indices_template
        FROM restreams
        WHERE slug = ? AND is_active = 1
        """,
        (slug,),
    ).fetchone()

    if not restream:
        abort(404)

    # Pas d'indices pour ce restream
    if restream["indices_template"] == "none":
        abort(404)

    session_file = indices_sessions_dir() / f"{slug}.json"
    if not session_file.exists():
        abort(404)

    with open(session_file, "r", encoding="utf-8") as f:
        indices_data = json.load(f)

    return render_template(
        "restream/indices.html",
        restream=restream,
        indices=indices_data,
        restream_slug=slug,
    )


# =========================================================
# MISE À JOUR D’UNE CATÉGORIE
# =========================================================

@restream_bp.route("/<slug>/indices/update-category", methods=["POST"])
@login_required
@role_required("éditeur")
def update_category(slug):
    session_file = indices_sessions_dir() / f"{slug}.json"

    if not session_file.exists():
        abort(404)

    data = request.get_json()
    if not data:
        abort(400)

    category = data.get("category")
    lines = data.get("lines")

    if not category or lines is None:
        abort(400)

    with open(session_file, "r", encoding="utf-8") as f:
        indices = json.load(f)

    if category not in indices["categories"]:
        abort(400)

    columns = indices["categories"][category]["columns"]
    items = []

    for line in lines:
        parts = [cell.strip() for cell in line.split("|")]

        if columns == 2:
            row = parts[:2] + [""] * (2 - len(parts))
        else:
            row = parts[:1]

        items.append(row)

    indices["categories"][category]["items"] = items

    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(indices, f, ensure_ascii=False, indent=2)

    return {"status": "ok"}


# =========================================================
# SERVER-SENT EVENTS (SSE)
# =========================================================

@restream_bp.route("/<slug>/indices/stream")
def stream_indices(slug):
    session_file = indices_sessions_dir() / f"{slug}.json"

    if not session_file.exists():
        abort(404)

    def event_stream():
        last_mtime = session_file.stat().st_mtime
        
        with open(session_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        while True:
            time.sleep(SSE_POLL_INTERVAL)

            current_mtime = session_file.stat().st_mtime
            if current_mtime != last_mtime:
                last_mtime = current_mtime

                with open(session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


# =========================================================
# RESET COMPLET DES INDICES (RECOPIE DU TEMPLATE)
# =========================================================

@restream_bp.route("/<slug>/indices/reset-all", methods=["POST"])
@login_required
@role_required("restreamer")
def reset_all_indices(slug):
    db = get_db()
    restream = db.execute(
        "SELECT indices_template FROM restreams WHERE slug = ?",
        (slug,)
    ).fetchone()

    if not restream or restream["indices_template"] == "none":
        abort(404)

    template_file = get_indices_template_path(restream["indices_template"])
    session_file = indices_sessions_dir() / f"{slug}.json"

    if not template_file.exists():
        abort(404, description="Template d’indices introuvable")
        
    session_file.parent.mkdir(parents=True, exist_ok=True)

    copyfile(template_file, session_file)

    return "", 204

@restream_bp.route("/<slug>/edit", methods=["GET", "POST"])
@login_required
@role_required("restreamer")
def edit(slug):
    db = get_db()

    restream = db.execute(
        """
        SELECT
            id,
            slug,
            title,
            twitch_url,
            restreamer_name,
            commentator_name,
            tracker_name,
            indices_template,
            tracker_type
        FROM restreams
        WHERE slug = ?
        """,
        (slug,),
    ).fetchone()

    if not restream:
        abort(404)

    if request.method == "POST":
        title = request.form.get("title")
        twitch_url = request.form.get("twitch_url") or None
        restreamer_name = request.form.get("restreamer_name") or None
        commentator_name = request.form.get("commentator_name") or None
        tracker_name = request.form.get("tracker_name") or None

        new_indices_template = request.form.get("indices_template")
        new_tracker_type = request.form.get("tracker_type")

        if not title or not new_indices_template or not new_tracker_type:
            flash("Tous les champs obligatoires doivent être remplis.", "error")
            return redirect(url_for("restream.edit", slug=slug))
            
        if not is_valid_indices_template(new_indices_template):
            flash("Template d’indices invalide.", "error")
            return redirect(url_for("restream.edit", slug=slug))
            
        if not is_valid_tracker_type(new_tracker_type):
            flash("Tracker invalide.", "error")
            return redirect(url_for("restream.edit", slug=slug))

        # --------------------------------------------------------------
        # Gestion des indices (delete & recreate)
        # --------------------------------------------------------------
        session_path = indices_sessions_dir() / f"{slug}.json"

        if new_indices_template != restream["indices_template"]:
            # supprimer l’ancienne session si elle existe
            if session_path.exists():
                session_path.unlink()

            # recréer seulement si != "none"
            if new_indices_template != "none":
                template_path = get_indices_template_path(new_indices_template)

                if not template_path.exists():
                    flash("Template d’indices introuvable.", "error")
                    return redirect(url_for("restream.edit", slug=slug))

                session_path.parent.mkdir(parents=True, exist_ok=True)
                copyfile(template_path, session_path)
                
        # --------------------------------------------------------------
        # Gestion du tracker (delete session si changement de type)
        # --------------------------------------------------------------
        if new_tracker_type != restream["tracker_type"]:
            tracker_session_path: Path = tracker_session_path_restream(int(restream["id"]))

            if tracker_session_path.exists():
                tracker_session_path.unlink()


        # --------------------------------------------------------------
        # Update DB
        # --------------------------------------------------------------
        db.execute(
            """
            UPDATE restreams
            SET
                title = ?,
                twitch_url = ?,
                restreamer_name = ?,
                commentator_name = ?,
                tracker_name = ?,
                indices_template = ?,
                tracker_type = ?
            WHERE slug = ?
            """,
            (
                title,
                twitch_url,
                restreamer_name,
                commentator_name,
                tracker_name,
                new_indices_template,
                new_tracker_type,
                slug,
            ),
        )
        db.commit()

        flash("Restream mis à jour.", "success")
        return redirect(url_for("restream.manage"))

    return render_template(
        "restream/edit.html",
        restream=restream,
        available_indices_templates=get_available_indices_templates(),
        available_tracker_types=get_available_trackers(),
    )




@restream_bp.get("/<slug>/live")
def restream_live(slug: str):
    db = get_db()

    restream = db.execute(
        """
        SELECT
            id,
            slug,
            title,
            match_id,
            is_active,
            indices_template,
            tracker_type
        FROM restreams
        WHERE slug = ? AND is_active = 1
        """,
        (slug,),
    ).fetchone()

    if not restream:
        abort(404)

    # --------------------------------------------------------------
    # Indices
    # --------------------------------------------------------------
    indices_data = None

    if restream["indices_template"] != "none":
        session_file = indices_sessions_dir() / f"{slug}.json"
        if not session_file.exists():
            abort(404)

        with open(session_file, "r", encoding="utf-8") as f:
            indices_data = json.load(f)

    # --------------------------------------------------------------
    # Permissions
    # --------------------------------------------------------------
    can_edit = current_user.is_authenticated and has_required_role(
        getattr(current_user, "role", None),
        "éditeur",
    )
    
    can_manage_tracker = (
        current_user.is_authenticated
        and has_required_role(getattr(current_user, "role", None), "restreamer")
    )

    tracker_payload = None

    # --------------------------------------------------------------
    # Tracker (uniquement si activé)
    # --------------------------------------------------------------
    if can_edit and restream["tracker_type"] != "none":

        tracker_type = restream["tracker_type"]

        # --- récupération de la définition du tracker ---
        try:
            tracker_def = get_tracker_definition(tracker_type)
        except KeyError:
            abort(500)  # tracker inconnu → incohérence DB

        # --- participants ---
        teams = db.execute(
            """
            SELECT t.id AS team_id, t.name AS team_name
            FROM match_teams mt
            JOIN teams t ON t.id = mt.team_id
            WHERE mt.match_id = ?
            ORDER BY mt.team_id ASC
            """,
            (restream["match_id"],),
        ).fetchall()

        participants_count = max(1, len(teams))

        # --- session tracker ---
        existing_session = load_session_restream(int(restream["id"]))

        session = ensure_session_restream(
            tracker_type=tracker_type,
            restream_id=int(restream["id"]),
            restream_slug=restream["slug"],
            preset_factory=tracker_def["default_preset"],
            participants_count=participants_count,
        )

        # --- injection slot / team / label UNIQUEMENT à la création ---
        if existing_session is None:
            for i, p in enumerate(session.get("participants", [])):
                p["slot"] = i + 1
                p.setdefault("show_final_time", False)
                if i < len(teams):
                    name = (teams[i]["team_name"] or f"Slot {i+1}").replace("Solo - ", "")
                    p["team_id"] = int(teams[i]["team_id"])
                    p["label"] = name
                else:
                    p.setdefault("team_id", 0)
                    p.setdefault("label", f"Slot {i+1}")
                
            save_session_restream(int(restream["id"]), session)

        # --- payload pour le template ---
        tracker_payload = {
            "tracker_type": tracker_type,
            "catalog": tracker_def["catalog"](),
            "session": session,
            "use_storage": False,
            "update_url": url_for(
                "restream.restream_tracker_update",
                slug=restream["slug"],
            ),
            "stream_url": url_for(
                "restream.restream_tracker_stream",
                slug=restream["slug"],
            ),
            "frontend": tracker_def["frontend"],
        }

    return render_template(
        "restream/live.html",
        restream=restream,
        restream_slug=slug,
        indices=indices_data,
        can_edit=can_edit,
        can_manage_tracker=can_manage_tracker,
        tracker=tracker_payload,
    )


@restream_bp.post("/<slug>/tracker/update")
@login_required
@role_required("éditeur")
def restream_tracker_update(slug: str):
    db = get_db()
    restream = db.execute(
        """
        SELECT id, slug, match_id, tracker_type
        FROM restreams
        WHERE slug = ? AND is_active = 1
        """,
        (slug,),
    ).fetchone()

    if not restream:
        abort(404)

    payload = request.get_json(silent=True) or {}
    participant = payload.get("participant")
    if not isinstance(participant, dict):
        abort(400, description="Payload invalide: participant manquant")

    slot = int(participant.get("slot", 1))
    if slot < 1:
        abort(400, description="slot invalide (doit être >= 1)")

    # s’assurer session existante
    teams = db.execute(
        """
        SELECT t.id AS team_id, t.name AS team_name
        FROM match_teams mt
        JOIN teams t ON t.id = mt.team_id
        WHERE mt.match_id = ?
        ORDER BY mt.team_id ASC
        """,
        (restream["match_id"],),
    ).fetchall()
    participants_count = max(1, len(teams))

    tracker_type = restream["tracker_type"]
    if tracker_type == "none":
        abort(404)

    try:
        tracker_def = get_tracker_definition(tracker_type)
    except KeyError:
        abort(500)

    session = ensure_session_restream(
        tracker_type=tracker_type,
        restream_id=int(restream["id"]),
        restream_slug=restream["slug"],
        preset_factory=tracker_def["default_preset"],
        participants_count=participants_count,
    )

    idx = slot - 1
    if idx >= len(session.get("participants", [])):
        abort(400, description="slot invalide (hors bornes session)")

    existing_p = session["participants"][idx]
    existing_p.update(participant)   # merge
    session["participants"][idx] = existing_p
    session["version"] = int(session.get("version", 0)) + 1

    save_session_restream(int(restream["id"]), session)
    return jsonify({"ok": True, "version": session["version"]})

@restream_bp.get("/<slug>/tracker/stream")
def restream_tracker_stream(slug: str):
    db = get_db()
    restream = db.execute(
        """
        SELECT id, slug, match_id, tracker_type
        FROM restreams
        WHERE slug = ? AND is_active = 1
        """,
        (slug,),
    ).fetchone()

    if not restream:
        abort(404)

    teams = db.execute(
        """
        SELECT t.id AS team_id, t.name AS team_name
        FROM match_teams mt
        JOIN teams t ON t.id = mt.team_id
        WHERE mt.match_id = ?
        ORDER BY mt.team_id ASC
        """,
        (restream["match_id"],),
    ).fetchall()

    participants_count = max(1, len(teams))

    
    tracker_type = restream["tracker_type"]
    if tracker_type == "none":
        abort(404)

    try:
        tracker_def = get_tracker_definition(tracker_type)
    except KeyError:
        abort(500)

    ensure_session_restream(
        tracker_type=tracker_type,
        restream_id=int(restream["id"]),
        restream_slug=restream["slug"],
        preset_factory=tracker_def["default_preset"],
        participants_count=participants_count,
    )

    session_file: Path = tracker_session_path_restream(int(restream["id"]))

    def read_session_json() -> dict:
        if not session_file.exists():
            return {}
        try:
            with session_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @stream_with_context
    def event_stream():
        last_mtime = session_file.stat().st_mtime if session_file.exists() else 0.0
        yield f"data: {json.dumps(read_session_json(), ensure_ascii=False)}\n\n"

        while True:
            time.sleep(SSE_POLL_INTERVAL)
            if not session_file.exists():
                continue
            mtime = session_file.stat().st_mtime
            if mtime != last_mtime:
                last_mtime = mtime
                yield f"data: {json.dumps(read_session_json(), ensure_ascii=False)}\n\n"

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return Response(event_stream(), mimetype="text/event-stream", headers=headers)

@restream_bp.get("/<slug>/tracker/presets")
@login_required
@role_required("restreamer")
def restream_tracker_presets(slug: str):
    db = get_db()
    restream = db.execute(
        "SELECT id, slug, match_id, tracker_type FROM restreams WHERE slug = ? AND is_active = 1",
        (slug,),
    ).fetchone()
    if not restream:
        abort(404)

    tracker_type = restream["tracker_type"]
    if tracker_type == "none":
        abort(404)

    tracker_def = get_tracker_definition(tracker_type)

    presets = list_presets(tracker_type)
    presets.sort(key=lambda p: (p.get("label") or "").lower())

    return render_template(
        "restream/tracker_presets.html",
        restream=restream,
        restream_slug=slug,
        tracker_type=tracker_type,
        tracker_label=tracker_def["label"],
        presets=presets,
    )

@restream_bp.post("/<slug>/tracker/presets/apply")
@login_required
@role_required("restreamer")
def restream_tracker_presets_apply(slug: str):
    db = get_db()
    restream = db.execute(
        "SELECT id, slug, match_id, tracker_type FROM restreams WHERE slug = ? AND is_active = 1",
        (slug,),
    ).fetchone()
    if not restream:
        abort(404)

    tracker_type = restream["tracker_type"]
    if tracker_type == "none":
        abort(404)

    tracker_def = get_tracker_definition(tracker_type)

    preset_slug = (request.form.get("preset_slug") or "").strip()
    if not preset_slug:
        abort(400, description="preset_slug manquant")

    preset = load_preset(tracker_type, preset_slug)
    preset_participant = preset.get("participant")
    if not isinstance(preset_participant, dict):
        abort(500, description="Preset invalide: participant manquant")

    # garantir que la session existe (même logique que chez toi)
    teams = db.execute(
        """
        SELECT t.id AS team_id, t.name AS team_name
        FROM match_teams mt
        JOIN teams t ON t.id = mt.team_id
        WHERE mt.match_id = ?
        ORDER BY mt.team_id ASC
        """,
        (restream["match_id"],),
    ).fetchall()
    participants_count = max(1, len(teams))

    session = ensure_session_restream(
        tracker_type=tracker_type,
        restream_id=int(restream["id"]),
        restream_slug=restream["slug"],
        preset_factory=tracker_def["default_preset"],
        participants_count=participants_count,
    )

    # applique à tous les slots, en préservant identité
    new_participants = []
    for i, existing in enumerate(session.get("participants", []), start=1):
        new_p = json.loads(json.dumps(preset_participant))  # deep copy simple
        new_p["slot"] = existing.get("slot", i)
        new_p["team_id"] = existing.get("team_id", 0)
        new_p["label"] = existing.get("label", f"Slot {i}")
        new_participants.append(new_p)

    session["participants"] = new_participants
    session["version"] = int(session.get("version", 0)) + 1
    save_session_restream(int(restream["id"]), session)

    flash("Preset chargé sur tous les slots.", "success")
    return redirect(url_for("restream.restream_live", slug=slug))


@restream_bp.post("/<slug>/tracker/reset")
@login_required
@role_required("restreamer")
def restream_tracker_reset(slug: str):
    db = get_db()
    restream = db.execute(
        "SELECT id, slug, match_id, tracker_type FROM restreams WHERE slug = ? AND is_active = 1",
        (slug,),
    ).fetchone()
    if not restream:
        abort(404)

    tracker_type = restream["tracker_type"]
    if tracker_type == "none":
        abort(404)

    tracker_def = get_tracker_definition(tracker_type)

    teams = db.execute(
        """
        SELECT t.id AS team_id, t.name AS team_name
        FROM match_teams mt
        JOIN teams t ON t.id = mt.team_id
        WHERE mt.match_id = ?
        ORDER BY mt.team_id ASC
        """,
        (restream["match_id"],),
    ).fetchall()
    participants_count = max(1, len(teams))

    session = ensure_session_restream(
        tracker_type=tracker_type,
        restream_id=int(restream["id"]),
        restream_slug=restream["slug"],
        preset_factory=tracker_def["default_preset"],
        participants_count=participants_count,
    )

    default_session = tracker_def["default_preset"](participants_count=participants_count)
    default_participants = default_session.get("participants", [])

    new_participants = []
    for i, existing in enumerate(session.get("participants", []), start=1):
        base = default_participants[i - 1] if i - 1 < len(default_participants) else {}
        new_p = json.loads(json.dumps(base))
        new_p["slot"] = existing.get("slot", i)
        new_p["team_id"] = existing.get("team_id", 0)
        new_p["label"] = existing.get("label", f"Slot {i}")
        new_participants.append(new_p)

    session["participants"] = new_participants
    session["version"] = int(session.get("version", 0)) + 1
    save_session_restream(int(restream["id"]), session)

    flash("Tracker reset (preset par défaut).", "success")
    return redirect(url_for("restream.restream_live", slug=slug))
    
@restream_bp.post("/<slug>/final-time/<int:slot>/toggle")
@login_required
@role_required("restreamer")
def restream_toggle_final_time(slug: str, slot: int):
    db = get_db()
    restream = db.execute(
        "SELECT id, slug, match_id, tracker_type FROM restreams WHERE slug = ? AND is_active = 1",
        (slug,),
    ).fetchone()
    if not restream:
        abort(404)

    tracker_type = restream["tracker_type"]
    if tracker_type == "none":
        abort(404)

    # On charge la session existante (si elle n'existe pas, on la crée via ensure)
    tracker_def = get_tracker_definition(tracker_type)

    teams = db.execute(
        """
        SELECT t.id AS team_id, t.name AS team_name
        FROM match_teams mt
        JOIN teams t ON t.id = mt.team_id
        WHERE mt.match_id = ?
        ORDER BY mt.team_id ASC
        """,
        (restream["match_id"],),
    ).fetchall()
    participants_count = max(1, len(teams))

    session = ensure_session_restream(
        tracker_type=tracker_type,
        restream_id=int(restream["id"]),
        restream_slug=restream["slug"],
        preset_factory=tracker_def["default_preset"],
        participants_count=participants_count,
    )

    participants = session.get("participants", [])
    target = None
    for p in participants:
        if int(p.get("slot", 0)) == slot:
            target = p
            break

    if not target:
        abort(404)

    current = bool(target.get("show_final_time", False))
    target["show_final_time"] = not current

    session["version"] = int(session.get("version", 0)) + 1
    save_session_restream(int(restream["id"]), session)

    flash(
        f"Temps final Joueur {slot} : {'ON' if target['show_final_time'] else 'OFF'}.",
        "success",
    )
    return redirect(url_for("restream.restream_live", slug=slug))


###############################################
#############  OVERLAYS #######################
###############################################

@restream_bp.get("/<slug>/overlay")
def restream_overlay(slug: str):
    db = get_db()

    restream = db.execute(
        """
        SELECT
            id,
            slug,
            title,
            match_id,
            is_active,
            commentator_name,
            tracker_type
        FROM restreams
        WHERE slug = ? AND is_active = 1
        """,
        (slug,),
    ).fetchone()

    if not restream:
        abort(404)

    # --------------------------------------------------------------
    # Tracker désactivé → overlay vide / 404
    # --------------------------------------------------------------
    if restream["tracker_type"] == "none":
        abort(404)

    tracker_type = restream["tracker_type"]

    # --------------------------------------------------------------
    # Récupération définition tracker
    # --------------------------------------------------------------
    try:
        tracker_def = get_tracker_definition(tracker_type)
    except KeyError:
        abort(500)  # incohérence DB

    # --------------------------------------------------------------
    # Participants (teams du match)
    # --------------------------------------------------------------
    teams = get_match_teams(db, restream["match_id"])

    participants_count = max(1, len(teams))
    
    # --------------------------------------------------------------
    # Racetime (twitch + temps final) pour overlay
    # --------------------------------------------------------------
    match_row = db.execute(
        "SELECT racetime_room FROM matches WHERE id = ?",
        (restream["match_id"],),
    ).fetchone()

    racetime_room = (match_row["racetime_room"] if match_row else "") or ""

    def team_racetime_users(team_id: int) -> list[str]:
        rows = db.execute(
            """
            SELECT p.racetime_user
            FROM team_players tp
            JOIN players p ON p.id = tp.player_id
            WHERE tp.team_id = ?
            ORDER BY tp.position ASC
            """,
            (team_id,),
        ).fetchall()
        return [r["racetime_user"] for r in rows if r["racetime_user"]]

    # best effort: on prend le 1er joueur de chaque team pour slot1/slot2
    left_rt_user = ""
    right_rt_user = ""

    if len(teams) > 0:
        left_users = team_racetime_users(int(teams[0]["team_id"]))
        left_rt_user = left_users[0] if left_users else ""

    if len(teams) > 1:
        right_users = team_racetime_users(int(teams[1]["team_id"]))
        right_rt_user = right_users[0] if right_users else ""

    left_twitch = ""
    right_twitch = ""
    left_time = ""
    right_time = ""
    left_status = ""
    right_status = ""

    if racetime_room:
        try:
            race_json = fetch_race_data(racetime_room)
            overlay_map = extract_entrants_overlay_info(race_json)

            left_info = overlay_map.get(left_rt_user)
            right_info = overlay_map.get(right_rt_user)

            if left_info:
                left_twitch = left_info.twitch_name
                left_status = left_info.status
                if left_info.status == "done":
                    left_time = left_info.finish_time_hms

            if right_info:
                right_twitch = right_info.twitch_name
                right_status = right_info.status
                if right_info.status == "done":
                    right_time = right_info.finish_time_hms

        except Exception:
            # overlay ne doit pas casser si Racetime est KO / URL invalide
            pass


    # --------------------------------------------------------------
    # Session tracker (création si absente)
    # --------------------------------------------------------------
    existing_session = load_session_restream(int(restream["id"]))

    session = ensure_session_restream(
        tracker_type=tracker_type,
        restream_id=int(restream["id"]),
        restream_slug=restream["slug"],
        preset_factory=tracker_def["default_preset"],
        participants_count=participants_count,
    )

    # --------------------------------------------------------------
    # Injection labels / team_id UNIQUEMENT à la création
    # --------------------------------------------------------------
    if existing_session is None:
        for i, p in enumerate(session.get("participants", [])):
            p["slot"] = i + 1
            p.setdefault("show_final_time", False)
            if i < len(teams):
                name = (teams[i]["team_name"] or f"Slot {i+1}").replace("Solo - ", "")
                p["team_id"] = int(teams[i]["team_id"])
                p["label"] = name
            else:
                p.setdefault("team_id", 0)
                p.setdefault("label", f"Slot {i+1}")

        save_session_restream(int(restream["id"]), session)

    # --------------------------------------------------------------
    # Payload tracker (read-only)
    # --------------------------------------------------------------
    tracker_payload = {
        "tracker_type": tracker_type,
        "catalog": tracker_def["catalog"](),
        "session": session,
        "use_storage": False,
        "frontend": tracker_def["frontend"],
        # SSE stream utilisé par OBS
        "stream_url": url_for(
            "restream.restream_tracker_stream",
            slug=restream["slug"],
        ),
        # update_url présent mais non utilisé (overlay read-only)
        "update_url": url_for(
            "restream.restream_tracker_update",
            slug=restream["slug"],
        ),
    }
    
    left = (teams[0]["team_name"] if len(teams) > 0 else "Slot 1") or "Slot 1"
    right = (teams[1]["team_name"] if len(teams) > 1 else "Slot 2") or "Slot 2"

    c1, c2 = split_commentators(restream["commentator_name"])
    
    # exemple logique côté route overlay
    left_show_time = False
    right_show_time = False

    for p in session.get("participants", []):
        if p.get("slot") == 1:
            left_show_time = bool(p.get("show_final_time", False))
        elif p.get("slot") == 2:
            right_show_time = bool(p.get("show_final_time", False))


    live_payload = {
        "left_name": left.replace("Solo - ", ""),
        "right_name": right.replace("Solo - ", ""),
        "title": simplify_restream_title(restream["title"]),
        "commentator_1": c1,
        "commentator_2": c2,
        "left_twitch": left_twitch,
        "right_twitch": right_twitch,
        "left_time": left_time,
        "right_time": right_time,
        "left_status": left_status,
        "right_status": right_status,
        "left_show_time": left_show_time,
        "right_show_time": right_show_time,
    }


    # IMPORTANT : overlay = toujours read-only
    can_edit = False
    
    overlay_pack = resolve_overlay_pack_for_match(db, restream["match_id"])

    return render_template(
        "restream/overlay_live.html",
        restream=restream,
        restream_slug=slug,
        tracker=tracker_payload,
        can_edit=can_edit,
        overlay_pack=overlay_pack,
        live=live_payload,
    )
    
@restream_bp.get("/<slug>/overlay/intro")
def restream_overlay_intro(slug: str):
    db = get_db()
    restream = get_active_restream_by_slug(db, slug)
    if not restream:
        abort(404)

    teams = get_match_teams(db, restream["match_id"])

    left = (teams[0]["team_name"] if len(teams) > 0 else "Slot 1") or "Slot 1"
    right = (teams[1]["team_name"] if len(teams) > 1 else "Slot 2") or "Slot 2"

    # tournament name
    row = db.execute(
        """
        SELECT t.name AS tournament_name
        FROM matches m
        JOIN tournaments t ON t.id = m.tournament_id
        WHERE m.id = ?
        """,
        (restream["match_id"],),
    ).fetchone()

    tournament_name = overlay_tournament_name(row["tournament_name"]) if row and row["tournament_name"] else ""

    overlay_pack = resolve_overlay_pack_for_match(db, restream["match_id"])
    
    display_title = simplify_restream_title(restream["title"])

    return render_template(
        "restream/overlay_intro.html",
        restream=restream,
        restream_slug=slug,
        intro={
            "tournament_name": tournament_name,
            "match_label": display_title,  # on réutilise le title comme label
            "left_name": left.replace("Solo - ", ""),
            "right_name": right.replace("Solo - ", ""),
        },
        overlay_pack=overlay_pack,
    )


MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre"
]
DAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _format_dt_fr(scheduled_at: str | None) -> str:
    if not scheduled_at:
        return ""
    # SQLite renvoie souvent "YYYY-MM-DD HH:MM:SS"
    try:
        dt = datetime.fromisoformat(scheduled_at.replace("Z", "").replace("T", " "))
    except ValueError:
        return scheduled_at

    day = DAYS_FR[dt.weekday()].capitalize()
    month = MONTHS_FR[dt.month - 1].capitalize()
    return f"{day} {dt.day} {month} - {dt:%Hh%M}"


@restream_bp.get("/<slug>/overlay/next")
def restream_overlay_next(slug: str):
    db = get_db()
    restream = get_active_restream_by_slug(db, slug)
    if not restream:
        abort(404)

    # tournoi courant (pour afficher le titre, même si next_match=None)
    row = db.execute(
        """
        SELECT
            t.id AS tournament_id,
            t.name AS tournament_name
        FROM matches m
        JOIN tournaments t ON t.id = m.tournament_id
        WHERE m.id = ?
        """,
        (restream["match_id"],),
    ).fetchone()

    tournament_id = row["tournament_id"] if row else None
    tournament_name = overlay_tournament_name(row["tournament_name"]) if row and row["tournament_name"] else ""
    

    overlay_pack = resolve_overlay_pack_for_match(db, restream["match_id"])

    next_match = get_next_planned_match_for_overlay(db, tournament_id=tournament_id, exclude_match_id=restream["match_id"])

    # Payload affichage (ou None)
    next_payload = None
    if next_match:
        teams = next_match.get("teams") or []
        left = (teams[0]["team_name"] if len(teams) > 0 else "Slot 1") or "Slot 1"
        right = (teams[1]["team_name"] if len(teams) > 1 else "Slot 2") or "Slot 2"

        label_raw = next_match.get("restream_title") or "Prochain match"
        label = simplify_restream_title(label_raw) or label_raw

        next_payload = {
            "left_name": left.replace("Solo - ", ""),
            "right_name": right.replace("Solo - ", ""),
            "label": label,
            "datetime_label": _format_dt_fr(next_match.get("scheduled_at")),
        }

    return render_template(
        "restream/overlay_next.html",
        restream=restream,
        restream_slug=slug,
        overlay_pack=overlay_pack,
        tournament_name=tournament_name,
        next=next_payload,
    )

@restream_bp.get("/<slug>/overlay/live-data")
def restream_overlay_live_data(slug: str):
    db = get_db()

    restream = db.execute(
        "SELECT id, slug, match_id, tracker_type FROM restreams WHERE slug = ? AND is_active = 1",
        (slug,),
    ).fetchone()
    if not restream or restream["tracker_type"] == "none":
        abort(404)

    # Match: racetime_room (URL complète)
    match_row = db.execute(
        "SELECT racetime_room FROM matches WHERE id = ?",
        (restream["match_id"],),
    ).fetchone()
    racetime_room = (match_row["racetime_room"] if match_row else "") or ""

    # Session pour connaitre team_id/slot (et racetime users via DB)
    session = load_session_restream(int(restream["id"])) or {}
    participants = session.get("participants", [])

    # helper: récupérer 1 racetime_user par team (slot)
    def team_racetime_user(team_id: int) -> str:
        row = db.execute(
            """
            SELECT p.racetime_user
            FROM team_players tp
            JOIN players p ON p.id = tp.player_id
            WHERE tp.team_id = ?
            ORDER BY tp.position ASC
            LIMIT 1
            """,
            (team_id,),
        ).fetchone()
        return (row["racetime_user"] if row else "") or ""

    # Prépare slots -> racetime_user
    slot_to_rt = {}
    for p in participants:
        slot = int(p.get("slot", 0) or 0)
        team_id = int(p.get("team_id", 0) or 0)
        if slot and team_id:
            slot_to_rt[str(slot)] = team_racetime_user(team_id)

    # Réponse vide si pas de racetime_room
    payload = {"slots": {}}

    if not racetime_room:
        return payload

    try:
        race_json = fetch_race_data(racetime_room)
        overlay_map = extract_entrants_overlay_info(race_json)

        for slot_str, rt_user in slot_to_rt.items():
            info = overlay_map.get(rt_user)
            if not info:
                payload["slots"][slot_str] = {"status": "", "time": ""}
                continue

            payload["slots"][slot_str] = {
                "status": info.status,
                "time": info.finish_time_hms if info.status == "done" else "",
            }

    except Exception:
        # fail-safe
        pass

    return payload

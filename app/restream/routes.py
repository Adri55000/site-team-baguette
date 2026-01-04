import json
from pathlib import Path
from flask import (
    Blueprint, render_template, abort,
    request, redirect, url_for, Response, flash, current_app, jsonify, stream_with_context
)
import time
from flask_login import current_user
from app.database import get_db
import os
from shutil import copyfile

from datetime import datetime

from app.auth.utils import login_required
from app.permissions.decorators import role_required
from app.permissions.roles import has_required_role
from app.modules.text import slugify
from app.modules.tracker.games.ssr import get_catalog
from app.modules.tracker.base import ensure_session_restream, save_session_restream, load_session_restream, build_session_from_preset, session_path_restream


# === Dossiers ===

INDICES_SESSIONS_DIR = Path("instance/indices/sessions")
INDICES_TEMPLATES_DIR = Path("instance/indices/templates")

SSE_POLL_INTERVAL = 0.25


restream_bp = Blueprint("restream", __name__, url_prefix="/restream")


def create_indices_session(slug, template_name):
    base_path = current_app.instance_path
    templates_dir = os.path.join(base_path, "indices", "templates")
    sessions_dir = os.path.join(base_path, "indices", "sessions")

    os.makedirs(sessions_dir, exist_ok=True)

    template_path = os.path.join(templates_dir, f"{template_name}.json")
    session_path = os.path.join(sessions_dir, f"{slug}.json")

    if not os.path.exists(template_path):
        raise FileNotFoundError("Template d’indices introuvable.")

    with open(template_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["updated_at"] = None

    with open(session_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)



@restream_bp.route("/")
def index():
    return render_template("restream/index.html")

@restream_bp.route("/<slug>")
def view(slug):
    db = get_db()
    restream = db.execute(
        """
        SELECT r.title, r.slug, r.twitch_url, r.created_at, r.restreamer_name, r.commentator_name, r.tracker_name,
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

    if request.method == "POST":
        title = request.form.get("title")
        match_id = request.form.get("match_id")
        indices_template = request.form.get("indices_template")
        twitch_url = request.form.get("twitch_url") or None
        restreamer_name = request.form.get("restreamer_name") or None
        commentator_name = request.form.get("commentator_name") or None
        tracker_name = request.form.get("tracker_name") or None

        if not title or not match_id or not indices_template:
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
            (match_id,)
        ).fetchone()

        if not match:
            flash("Match invalide ou déjà associé à un restream.", "error")
            return redirect(url_for("restream.create"))

        slug = slugify(title)

        indices_root = Path(current_app.instance_path) / "indices"
        templates_dir = indices_root / "templates"
        sessions_dir = indices_root / "sessions"

        sessions_dir.mkdir(parents=True, exist_ok=True)

        template_path = templates_dir / f"{indices_template}.json"
        target_path = sessions_dir / f"{slug}.json"

        if not template_path.exists():
            flash("Template d’indices introuvable.", "error")
            return redirect(url_for("restream.create"))

        copyfile(template_path, target_path)

        db.execute(
            """
            INSERT INTO restreams
                (slug, title, created_by, match_id, indices_template, twitch_url, restreamer_name, commentator_name, tracker_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slug,
                title,
                current_user.id,
                match_id,
                indices_template,
                twitch_url,
                restreamer_name,
                commentator_name,
                tracker_name,
            ),
        )
        db.commit()

        flash("Restream créé avec succès.", "success")
        return redirect(url_for("restream.manage"))

    # -----------------------------
    # GET : matchs éligibles
    # -----------------------------
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
        matches=matches
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

    template_file = INDICES_TEMPLATES_DIR / f"{restream['indices_template']}.json"
    session_file = INDICES_SESSIONS_DIR / f"{slug}.json"

    if not template_file.exists():
        abort(404, description="Template d’indices introuvable")

    copyfile(template_file, session_file)


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
    session_file = INDICES_SESSIONS_DIR / f"{slug}.json"
    if session_file.exists():
        session_file.unlink()


    flash("Restream désactivé.", "success")
    return redirect(url_for("restream.manage"))



# =========================================================
# PAGE INDICES D’UN RESTREAM (LECTURE)
# =========================================================

@restream_bp.route("/<slug>/indices")
def restream_indices(slug):
    session_file = INDICES_SESSIONS_DIR / f"{slug}.json"

    if not session_file.exists():
        abort(404)

    db = get_db()
    restream = db.execute(
        "SELECT title FROM restreams WHERE slug = ? AND is_active = 1",
        (slug,)
    ).fetchone()

    if not restream:
        abort(404)

    with open(session_file, "r", encoding="utf-8") as f:
        indices_data = json.load(f)

    return render_template(
        "restream/indices.html",
        restream=restream,
        indices=indices_data,
        restream_slug=slug
    )


# =========================================================
# MISE À JOUR D’UNE CATÉGORIE
# =========================================================

@restream_bp.route("/<slug>/indices/update-category", methods=["POST"])
@login_required
@role_required("éditeur")
def update_category(slug):
    session_file = INDICES_SESSIONS_DIR / f"{slug}.json"

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
    session_file = INDICES_SESSIONS_DIR / f"{slug}.json"

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

    if not restream:
        abort(404)

    template_file = INDICES_TEMPLATES_DIR / f"{restream['indices_template']}.json"
    session_file = INDICES_SESSIONS_DIR / f"{slug}.json"

    if not template_file.exists():
        abort(404, description="Template d’indices introuvable")

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
            tracker_name
        FROM restreams
        WHERE slug = ?
        """,
        (slug,)
    ).fetchone()

    if not restream:
        abort(404)

    if request.method == "POST":
        title = request.form.get("title")
        twitch_url = request.form.get("twitch_url") or None
        restreamer_name = request.form.get("restreamer_name") or None
        commentator_name = request.form.get("commentator_name") or None
        tracker_name = request.form.get("tracker_name") or None

        if not title:
            flash("Le titre est obligatoire.", "error")
            return redirect(url_for("restream.edit", slug=slug))

        db.execute(
            """
            UPDATE restreams
            SET
                title = ?,
                twitch_url = ?,
                restreamer_name = ?,
                commentator_name = ?,
                tracker_name = ?
            WHERE slug = ?
            """,
            (
                title,
                twitch_url,
                restreamer_name,
                commentator_name,
                tracker_name,
                slug,
            )
        )
        db.commit()

        flash("Restream mis à jour.", "success")
        return redirect(url_for("restream.manage"))

    return render_template(
        "restream/edit.html",
        restream=restream
    )



@restream_bp.get("/<slug>/live")
def restream_live(slug: str):
    db = get_db()

    restream = db.execute(
        """
        SELECT id, slug, title, match_id, is_active
        FROM restreams
        WHERE slug = ? AND is_active = 1
        """,
        (slug,),
    ).fetchone()

    if not restream:
        abort(404)

    # Indices: même logique que /<slug>/indices
    session_file = INDICES_SESSIONS_DIR / f"{slug}.json"
    if not session_file.exists():
        abort(404)

    with open(session_file, "r", encoding="utf-8") as f:
        indices_data = json.load(f)

    can_edit = current_user.is_authenticated and has_required_role(
        getattr(current_user, "role", None),
        "éditeur",
    )

    tracker_payload = None

    if can_edit:
        # participants_count basé sur teams du match
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

        tracker_type = "ssr_inventory"
        catalog = get_catalog()

        existing_session = load_session_restream(int(restream["id"]))
        session = ensure_session_restream(
            tracker_type=tracker_type,
            restream_id=int(restream["id"]),
            restream_slug=restream["slug"],
            catalog=catalog,
            participants_count=participants_count,
        )

        # inject labels/team_id à la création uniquement
        if existing_session is None:
            for i, p in enumerate(session.get("participants", [])):
                p["slot"] = i + 1
                if i < len(teams):
                    name = (teams[i]["team_name"] or f"Slot {i+1}").replace("Solo - ", "")
                    p["team_id"] = int(teams[i]["team_id"])
                    p["label"] = name
                else:
                    p.setdefault("team_id", 0)
                    p.setdefault("label", f"Slot {i+1}")
            save_session_restream(int(restream["id"]), session)

        tracker_payload = {
            "tracker_type": tracker_type,
            "catalog": catalog,
            "session": session,
            "use_storage": False,
            "update_url": url_for("restream.restream_tracker_update", slug=restream["slug"]),
            "stream_url": url_for("restream.restream_tracker_stream", slug=restream["slug"]),
        }

    return render_template(
        "restream/live.html",
        restream=restream,
        restream_slug=slug,
        indices=indices_data,
        can_edit=can_edit,
        tracker=tracker_payload,
    )

@restream_bp.post("/<slug>/tracker/update")
@login_required
@role_required("éditeur")
def restream_tracker_update(slug: str):
    db = get_db()
    restream = db.execute(
        """
        SELECT id, slug, match_id
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

    tracker_type = "ssr_inventory"
    catalog = get_catalog()

    session = ensure_session_restream(
        tracker_type=tracker_type,
        restream_id=int(restream["id"]),
        restream_slug=restream["slug"],
        catalog=catalog,
        participants_count=participants_count,
    )

    idx = slot - 1
    if idx >= len(session.get("participants", [])):
        abort(400, description="slot invalide (hors bornes session)")

    session["participants"][idx] = participant
    session["version"] = int(session.get("version", 0)) + 1

    save_session_restream(int(restream["id"]), session)
    return jsonify({"ok": True, "version": session["version"]})

@restream_bp.get("/<slug>/tracker/stream")
def restream_tracker_stream(slug: str):
    db = get_db()
    restream = db.execute(
        """
        SELECT id, slug, match_id
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

    tracker_type = "ssr_inventory"
    catalog = get_catalog()

    ensure_session_restream(
        tracker_type=tracker_type,
        restream_id=int(restream["id"]),
        restream_slug=restream["slug"],
        catalog=catalog,
        participants_count=participants_count,
    )

    session_file: Path = session_path_restream(int(restream["id"]))

    def read_session_json() -> dict:
        if not session_file.exists():
            return {}
        with session_file.open("r", encoding="utf-8") as f:
            return json.load(f)

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


@restream_bp.get("/<slug>/overlay")
def restream_overlay(slug: str):
    db = get_db()

    restream = db.execute(
        """
        SELECT id, slug, title, match_id, is_active
        FROM restreams
        WHERE slug = ? AND is_active = 1
        """,
        (slug,),
    ).fetchone()

    if not restream:
        abort(404)

    # participants_count basé sur les teams du match
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

    tracker_type = "ssr_inventory"
    catalog = get_catalog()

    existing_session = load_session_restream(int(restream["id"]))
    session = ensure_session_restream(
        tracker_type=tracker_type,
        restream_id=int(restream["id"]),
        restream_slug=restream["slug"],
        catalog=catalog,
        participants_count=participants_count,
    )

    # inject labels/team_id à la création uniquement (même logique que live)
    if existing_session is None:
        for i, p in enumerate(session.get("participants", [])):
            p["slot"] = i + 1
            if i < len(teams):
                name = (teams[i]["team_name"] or f"Slot {i+1}").replace("Solo - ", "")
                p["team_id"] = int(teams[i]["team_id"])
                p["label"] = name
            else:
                p.setdefault("team_id", 0)
                p.setdefault("label", f"Slot {i+1}")
        save_session_restream(int(restream["id"]), session)

    tracker_payload = {
        "tracker_type": tracker_type,
        "catalog": catalog,
        "session": session,
        "use_storage": False,
        # update_url pas utilisé en overlay (can_edit=false), mais on peut le laisser
        "update_url": url_for("restream.restream_tracker_update", slug=restream["slug"]),
        "stream_url": url_for("restream.restream_tracker_stream", slug=restream["slug"]),
    }

    # IMPORTANT: overlay = read-only
    can_edit = False

    return render_template(
        "restream/overlay.html",
        restream=restream,
        restream_slug=slug,
        tracker=tracker_payload,
        can_edit=can_edit,
    )

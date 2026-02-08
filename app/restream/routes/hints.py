import json
import time
from shutil import copyfile

from flask import Response, abort, render_template, request

from .. import restream_bp

from app.database import get_db
from app.auth.utils import login_required
from app.permissions.decorators import role_required

from app.restream.constants import SSE_POLL_INTERVAL
from app.restream.paths import indices_sessions_dir, indices_templates_dir

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


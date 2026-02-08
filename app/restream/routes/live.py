import json
from pathlib import Path
import time
from flask import render_template, abort, request, redirect, url_for, flash, jsonify, stream_with_context, Response
from flask_login import current_user
from flask_babel import gettext as _

from .. import restream_bp

from app.database import get_db
from app.auth.utils import login_required
from app.permissions.decorators import role_required
from app.permissions.roles import has_required_role

from app.modules.tracker.registry import get_tracker_definition
from app.modules.tracker.presets import list_presets, load_preset
from app.modules.tracker.base import (
    ensure_session_restream,
    load_session_restream,
    save_session_restream,
)

from app.restream.paths import indices_sessions_dir, tracker_session_path_restream
from app.restream.constants import SSE_POLL_INTERVAL


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
        
    match = db.execute(
        """
        SELECT id, racetime_room
        FROM matches
        WHERE id = ?
        """,
        (restream["match_id"],),
    ).fetchone()


    return render_template(
        "restream/live.html",
        restream=restream,
        match=match,
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

    flash(_("Preset chargé sur tous les slots."), "success")
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

    flash(_("Tracker reset (preset par défaut)."), "success")
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
        _("Temps final Joueur %(slot)s : %(state)s .", slot=slot, state= 'ON' if target['show_final_time'] else 'OFF'),
        "success",
    )
    return redirect(url_for("restream.restream_live", slug=slug))

@restream_bp.post("/<slug>/live/set-room-racetime")
@login_required
@role_required("restreamer")
def live_set_room_racetime(slug: str):
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

    room = (request.form.get("racetime_room") or "").strip()

    # petite validation “safe” (évite les valeurs vides / trop longues)
    if not room:
        flash(_("Room racetime vide."), "error")
        return redirect(url_for("restream.restream_live", slug=slug))

    if len(room) > 200:
        flash(_("Room racetime trop longue."), "error")
        return redirect(url_for("restream.restream_live", slug=slug))

    db.execute(
        """
        UPDATE matches
        SET racetime_room = ?
        WHERE id = ?
        """,
        (room, restream["match_id"]),
    )
    db.commit()

    flash(_("Room racetime enregistrée sur le match."), "success")
    return redirect(url_for("restream.restream_live", slug=slug))
    
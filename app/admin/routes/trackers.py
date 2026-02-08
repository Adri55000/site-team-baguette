import json

from flask import (
    request,
    render_template,
    redirect,
    url_for,
    flash,
)
from app.auth.utils import login_required
from flask_babel import _

from .. import admin_bp
from app.permissions.decorators import role_required

from app.modules.tracker.registry import get_available_trackers, get_tracker_definition
from app.modules.tracker.presets import list_presets, create_preset, load_preset, save_preset, rename_preset, delete_preset

@admin_bp.route("/trackers")
@login_required
@role_required("admin")
def admin_trackers_index():
    """
    Admin – List available trackers with presets count.
    """
    trackers = get_available_trackers()

    trackers_list = []

    for tracker in trackers:
        tracker_type = tracker["key"]

        try:
            presets = list_presets(tracker_type)
            presets_count = len(presets)
        except Exception:
            presets_count = 0

        trackers_list.append({
            "tracker_type": tracker_type,
            "label": tracker["label"],
            "presets_count": presets_count,
        })

    trackers_list.sort(key=lambda x: x["label"].lower())

    return render_template(
        "admin/trackers/index.html",
        trackers=trackers_list,
    )

    
@admin_bp.route("/trackers/<tracker_type>/presets")
@login_required
@role_required("admin")
def admin_trackers_presets(tracker_type):
    """
    Admin – List presets for a given tracker.
    """
    tracker_def = get_tracker_definition(tracker_type)

    presets = list_presets(tracker_type)

    # Tri UX (label)
    presets.sort(key=lambda x: (x.get("label") or "").lower())

    return render_template(
        "admin/trackers/presets_list.html",
        tracker_type=tracker_type,
        tracker_label=tracker_def["label"],
        presets=presets,
    )
    
    
def _get_default_participant_for_tracker(tracker_type: str) -> dict:
    """
    Génère un participant (1 slot) via la factory default_preset du registry.
    Supporte {"participants": [...]} et fallback participant dict.
    """
    tracker_def = get_tracker_definition(tracker_type)
    preset_factory = tracker_def["default_preset"]

    data = preset_factory(participants_count=1)

    if isinstance(data, dict) and "participants" in data and data["participants"]:
        participant = data["participants"][0]
    elif isinstance(data, dict):
        participant = data
    else:
        raise ValueError(
            f"Invalid default preset structure for tracker_type={tracker_type}"
        )

    participant.setdefault("slot", 1)
    participant.setdefault("team_id", 1)
    participant.setdefault("label", "Preset")

    return participant
    
@admin_bp.route("/trackers/<tracker_type>/presets/new", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_trackers_preset_new(tracker_type):
    tracker_def = get_tracker_definition(tracker_type)

    if request.method == "POST":
        label = (request.form.get("label") or "").strip()
        notes = (request.form.get("notes") or "").strip()
        participant_json = request.form.get("participant_json") or "{}"

        if not label:
            flash(_("Le nom du preset est obligatoire."), "error")
        else:
            try:
                participant = json.loads(participant_json)
            except Exception:
                participant = {}

            preset_slug = create_preset(
                tracker_type=tracker_type,
                label=label,
                participant=participant,
                notes=notes,
            )
            flash(_("Preset créé."), "success")
            return redirect(url_for(
                "admin.admin_trackers_preset_edit",
                tracker_type=tracker_type,
                preset_slug=preset_slug
            ))

    participant = _get_default_participant_for_tracker(tracker_type)
    tracker_catalog = tracker_def["catalog"]()

    return render_template(
        "admin/trackers/preset_edit.html",
        mode="new",
        tracker_type=tracker_type,
        tracker_label=tracker_def["label"],
        preset_slug=None,
        label="",
        notes="",
        participant=participant,
        tracker_catalog=tracker_catalog,
        tracker_frontend=tracker_def["frontend"],
    )


@admin_bp.route("/trackers/<tracker_type>/presets/<preset_slug>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_trackers_preset_edit(tracker_type, preset_slug):
    tracker_def = get_tracker_definition(tracker_type)
    preset = load_preset(tracker_type, preset_slug)

    if request.method == "POST":
        new_label = (request.form.get("label") or "").strip()
        notes = (request.form.get("notes") or "").strip()
        participant_json = request.form.get("participant_json") or "{}"

        if not new_label:
            flash(_("Le nom du preset est obligatoire."), "error")
        else:
            try:
                participant = json.loads(participant_json)
            except Exception:
                participant = {}

            # Rename si label change
            current_label = preset.get("label", "")
            if new_label != current_label:
                preset_slug = rename_preset(tracker_type, preset_slug, new_label)

            # Save contenu
            data = preset
            data["label"] = new_label
            data["notes"] = notes
            data["participant"] = participant

            save_preset(tracker_type, preset_slug, data)

            flash(_("Preset enregistré."), "success")
            return redirect(url_for(
                "admin.admin_trackers_preset_edit",
                tracker_type=tracker_type,
                preset_slug=preset_slug
            ))
    tracker_catalog = tracker_def["catalog"]()

    return render_template(
        "admin/trackers/preset_edit.html",
        mode="edit",
        tracker_type=tracker_type,
        tracker_label=tracker_def["label"],
        preset_slug=preset_slug,
        label=preset.get("label", preset_slug),
        notes=preset.get("notes", ""),
        participant=preset.get("participant", {}),
        tracker_catalog=tracker_catalog,
        tracker_frontend=tracker_def["frontend"],
    )
    
@admin_bp.route(
    "/trackers/<tracker_type>/presets/<preset_slug>/delete",
    methods=["POST"],
)
@login_required
@role_required("admin")
def admin_trackers_preset_delete(tracker_type, preset_slug):
    """
    Admin – Delete a preset.
    """
    # Vérifie que le tracker existe (cohérence UX)
    get_tracker_definition(tracker_type)

    try:
        delete_preset(tracker_type, preset_slug)
        flash(_("Preset supprimé."), "success")
    except FileNotFoundError:
        flash(_("Preset introuvable."), "error")

    return redirect(
        url_for(
            "admin.admin_trackers_presets",
            tracker_type=tracker_type,
        )
    )
    

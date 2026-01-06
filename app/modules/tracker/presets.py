import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import re


# ---------------------------------------------------------------------------
# Paths & helpers
# ---------------------------------------------------------------------------

INSTANCE_PRESETS_DIR = Path("instance/trackers/presets")


def _tracker_presets_dir(tracker_type: str) -> Path:
    """
    Return the directory containing presets for a tracker_type.
    """
    return INSTANCE_PRESETS_DIR / tracker_type


def _preset_path(tracker_type: str, preset_slug: str) -> Path:
    """
    Return the full path to a preset file.
    """
    return _tracker_presets_dir(tracker_type) / f"{preset_slug}.json"


def _now_iso() -> str:
    """
    Return current datetime as ISO 8601 string.
    """
    return datetime.now().isoformat(timespec="seconds")


def _slugify(label: str) -> str:
    """
    Slugify a preset label for use as filename.
    """
    slug = label.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = slug.strip("-")
    return slug or "preset"


def _ensure_unique_slug(tracker_type: str, base_slug: str) -> str:
    """
    Ensure the slug is unique in the tracker preset directory.
    Adds -2, -3, ... suffixes if needed.
    """
    presets_dir = _tracker_presets_dir(tracker_type)
    slug = base_slug
    counter = 2

    while _preset_path(tracker_type, slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def list_presets(tracker_type: str) -> List[Dict[str, Any]]:
    """
    List presets for a tracker_type.
    Returns minimal metadata for display.
    """
    presets_dir = _tracker_presets_dir(tracker_type)
    if not presets_dir.exists():
        return []

    presets: List[Dict[str, Any]] = []
    for path in presets_dir.glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            presets.append({
                "slug": path.stem,
                "label": data.get("label", path.stem),
                "notes": data.get("notes", ""),
                "updated_at": data.get("updated_at"),
            })
        except Exception:
            # Invalid preset file: skip silently
            continue

    return sorted(presets, key=lambda p: (p.get("label") or "").lower())



def load_preset(tracker_type: str, preset_slug: str) -> Dict[str, Any]:
    """
    Load and return a preset.
    """
    path = _preset_path(tracker_type, preset_slug)
    if not path.exists():
        raise FileNotFoundError(f"Preset not found: {preset_slug}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("tracker_type") != tracker_type:
        raise ValueError("Preset tracker_type mismatch")

    return data


def save_preset(tracker_type: str, preset_slug: str, data: Dict[str, Any]) -> None:
    """
    Save an existing preset.
    """
    presets_dir = _tracker_presets_dir(tracker_type)
    presets_dir.mkdir(parents=True, exist_ok=True)

    data["tracker_type"] = tracker_type
    data["updated_at"] = _now_iso()

    path = _preset_path(tracker_type, preset_slug)
    tmp_path = path.with_suffix(".json.tmp")

    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    os.replace(tmp_path, path)


def create_preset(
    tracker_type: str,
    label: str,
    participant: Dict[str, Any],
    notes: str = ""
) -> str:
    """
    Create a new preset and return its slug.
    """
    presets_dir = _tracker_presets_dir(tracker_type)
    presets_dir.mkdir(parents=True, exist_ok=True)

    base_slug = _slugify(label)
    slug = _ensure_unique_slug(tracker_type, base_slug)

    now = _now_iso()
    data = {
        "label": label,
        "tracker_type": tracker_type,
        "created_at": now,
        "updated_at": now,
        "notes": notes,
        "participant": participant,
    }

    save_preset(tracker_type, slug, data)
    return slug


def rename_preset(tracker_type: str, old_slug: str, new_label: str) -> str:
    """
    Rename a preset (file + label).
    Returns the new slug.
    """
    old_path = _preset_path(tracker_type, old_slug)
    if not old_path.exists():
        raise FileNotFoundError(f"Preset not found: {old_slug}")

    with old_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    base_slug = _slugify(new_label)
    new_slug = _ensure_unique_slug(tracker_type, base_slug)
    new_path = _preset_path(tracker_type, new_slug)

    data["label"] = new_label
    data["updated_at"] = _now_iso()

    tmp_path = new_path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    os.replace(tmp_path, new_path)

    old_path.unlink()
    return new_slug


def delete_preset(tracker_type: str, preset_slug: str) -> None:
    """
    Delete a preset file.
    """
    path = _preset_path(tracker_type, preset_slug)
    if not path.exists():
        raise FileNotFoundError(f"Preset not found: {preset_slug}")

    path.unlink()

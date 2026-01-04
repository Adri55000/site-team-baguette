"""
Tracker module — base utilities (presets & sessions storage).

Objectifs :
- Presets (modèles) : instance/trackers/presets/<tracker_type>/default.json
- Sessions (runtime) : instance/trackers/sessions/restream_<id>.json
- I/O JSON atomique
- Génération auto du preset default si absent, à partir du catalog (fourni par games/*.py)
- Initialisation auto d'une session si absente, à partir du preset default

Aucune logique UI/SSE ici : uniquement stockage + structure de state.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from flask import current_app

# ---------------------------------------------------------------------------
# Constantes / format
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1
DEFAULT_PRESET_NAME = "default"

# Sources supportées (extensible)
SOURCE_KIND_RESTREAM = "restream"


# ---------------------------------------------------------------------------
# Helpers temps / fichiers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Timestamp ISO local (avec timezone), utile pour debug/diag."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    """
    Ecriture atomique :
    - écrit dans un .tmp
    - os.replace => swap atomique sur la plupart des FS
    """
    _ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Paths (instance/trackers/...)
# ---------------------------------------------------------------------------

def trackers_root_dir() -> Path:
    return Path(current_app.instance_path) / "trackers"


def presets_root_dir() -> Path:
    return trackers_root_dir() / "presets"


def sessions_root_dir() -> Path:
    return trackers_root_dir() / "sessions"


def preset_path(tracker_type: str, preset_name: str = DEFAULT_PRESET_NAME) -> Path:
    return presets_root_dir() / tracker_type / f"{preset_name}.json"


def session_path_restream(restream_id: int) -> Path:
    # On choisit l'id (int) pour stabilité/unicité.
    return sessions_root_dir() / f"{SOURCE_KIND_RESTREAM}_{int(restream_id)}.json"


# ---------------------------------------------------------------------------
# Construction preset/session (générique)
# ---------------------------------------------------------------------------

def build_default_preset_from_catalog(tracker_type: str, catalog: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construit un preset "default" (état vide) à partir du catalog.

    Règles :
    - Ignore les items composite (tablets/triforces sont gérés à part)
    - Pour chaque item non composite :
        - si level_values => valeur = premier niveau
        - sinon => 0
    - Initialise dungeons/tablets/triforces à 0/False
    """
    items: Dict[str, Any] = {}

    for it in catalog.get("items", []):
        if it.get("kind") == "composite":
            continue
        item_id = it["id"]
        if it.get("level_values"):
            items[item_id] = it["level_values"][0]
        else:
            items[item_id] = 0

    preset = {
        "schema_version": SCHEMA_VERSION,
        "tracker_type": tracker_type,
        "preset_name": DEFAULT_PRESET_NAME,
        "items": items,
        "wallet_bonus": 0,
        "dungeons": {
            "SV": 0, "ET": 0, "LMF": 0, "AC": 0, "SSH": 0, "FS": 0, "SK": 0
        },
        "tablets": {"emerald": False, "ruby": False, "amber": False},
        "triforces": {"wisdom": False, "power": False, "courage": False},
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    return preset


def build_participant_from_preset(
    preset: Dict[str, Any],
    slot: int,
    label: Optional[str] = None,
    team_id: int = 0,
) -> Dict[str, Any]:
    """
    Transforme un preset (état d'un slot) en participant de session.
    """
    return {
        "slot": int(slot),
        "team_id": int(team_id),
        "label": label or f"Slot {int(slot)}",
        "items": dict(preset.get("items", {})),
        "wallet_bonus": int(preset.get("wallet_bonus", 0)),
        "dungeons": dict(preset.get("dungeons", {})),
        "tablets": dict(preset.get("tablets", {})),
        "triforces": dict(preset.get("triforces", {})),
    }


def build_session_from_preset(
    tracker_type: str,
    preset_name: str,
    preset: Dict[str, Any],
    source_kind: str,
    source_id: int,
    source_slug: Optional[str] = None,
    participants_count: int = 1,
) -> Dict[str, Any]:
    """
    Construit une session runtime (N participants) à partir d'un preset.
    """
    participants = [
        build_participant_from_preset(preset, slot=i + 1)
        for i in range(int(participants_count))
    ]

    session = {
        "schema_version": SCHEMA_VERSION,
        "tracker_type": tracker_type,
        "preset_name": preset_name,
        "version": 1,
        "source": {
            "kind": source_kind,
            "id": int(source_id),
            "slug": source_slug,
        },
        "participants": participants,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    return session


# ---------------------------------------------------------------------------
# API Presets
# ---------------------------------------------------------------------------

def load_preset(tracker_type: str, preset_name: str = DEFAULT_PRESET_NAME) -> Optional[Dict[str, Any]]:
    return _read_json(preset_path(tracker_type, preset_name))


def ensure_default_preset(tracker_type: str, catalog: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retourne le preset default.
    Si absent, le crée depuis le catalog.
    """
    path = preset_path(tracker_type, DEFAULT_PRESET_NAME)
    data = _read_json(path)
    if data is not None:
        return data

    data = build_default_preset_from_catalog(tracker_type, catalog)
    _write_json_atomic(path, data)
    return data


def save_preset(tracker_type: str, preset_name: str, preset: Dict[str, Any]) -> None:
    preset = dict(preset)
    preset["updated_at"] = _now_iso()
    _write_json_atomic(preset_path(tracker_type, preset_name), preset)


# ---------------------------------------------------------------------------
# API Sessions (restream)
# ---------------------------------------------------------------------------

def load_session_restream(restream_id: int) -> Optional[Dict[str, Any]]:
    return _read_json(session_path_restream(restream_id))


def save_session_restream(restream_id: int, session: Dict[str, Any]) -> None:
    session = dict(session)
    session["updated_at"] = _now_iso()
    _write_json_atomic(session_path_restream(restream_id), session)


def ensure_session_restream(
    tracker_type: str,
    restream_id: int,
    restream_slug: Optional[str],
    catalog: Dict[str, Any],
    participants_count: int = 1,
) -> Dict[str, Any]:
    """
    Retourne la session runtime pour un restream.
    - Si elle n'existe pas => la crée depuis preset default (auto-généré si absent).
    """
    existing = load_session_restream(restream_id)
    if existing is not None:
        return existing

    preset = ensure_default_preset(tracker_type, catalog)
    session = build_session_from_preset(
        tracker_type=tracker_type,
        preset_name=DEFAULT_PRESET_NAME,
        preset=preset,
        source_kind=SOURCE_KIND_RESTREAM,
        source_id=int(restream_id),
        source_slug=restream_slug,
        participants_count=participants_count,
    )
    save_session_restream(restream_id, session)
    return session

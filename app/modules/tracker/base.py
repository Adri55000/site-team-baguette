"""
Base tracker utilities (GENERIC).

Responsabilités :
- lecture / écriture des sessions tracker
- construction d’une session runtime à partir d’un preset
- initialisation d’une session si elle n’existe pas encore

NE FAIT PAS :
- définir des presets
- connaître un jeu / un catalog
- connaître le frontend
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from flask import current_app


# ======================================================================
# Paths & IO
# ======================================================================

def _sessions_dir() -> Path:
    return (
        Path(current_app.instance_path)
        / "trackers"
        / "sessions"
    )


def _session_path_restream(restream_id: int) -> Path:
    return _sessions_dir() / f"restream_{restream_id}.json"


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path: Path, data: Dict[str, Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    tmp_path.replace(path)


# ======================================================================
# Session builders (GENERIC)
# ======================================================================

def build_participant_from_preset(preset_participant: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construit un participant runtime à partir du preset.
    On copie TOUTES les clés du participant (shape spécifique au jeu),
    pour éviter de hardcoder un format unique.
    """
    # shallow copy suffisant (les sous-dicts sont du JSON simple)
    return dict(preset_participant)


def build_session_from_preset(
    preset: Dict[str, Any],
    tracker_type: str,
    restream_id: int,
    restream_slug: str,
) -> Dict[str, Any]:
    """
    Construit une session runtime complète à partir d’un preset.
    """
    participants = []

    for p in preset.get("participants", []):
        participants.append(build_participant_from_preset(p))

    return {
        "tracker_type": tracker_type,
        "restream_id": restream_id,
        "restream_slug": restream_slug,
        "participants": participants,
    }


# ======================================================================
# Public API
# ======================================================================

def load_session_restream(restream_id: int) -> Optional[Dict[str, Any]]:
    """
    Charge une session existante si elle existe.
    """
    path = _session_path_restream(restream_id)

    if not path.exists():
        return None

    try:
        return _read_json(path)
    except Exception:
        # Optionnel: log pour debug
        current_app.logger.warning(
            "Tracker session JSON invalide (restream_id=%s) -> reset",
            restream_id,
        )
        return None


def save_session_restream(restream_id: int, session: Dict[str, Any]):
    """
    Sauvegarde une session tracker.
    """
    path = _session_path_restream(restream_id)
    _write_json_atomic(path, session)


def ensure_session_restream(
    *,
    tracker_type: str,
    restream_id: int,
    restream_slug: str,
    preset_factory,
    participants_count: int,
) -> Dict[str, Any]:
    """
    Garantit qu’une session existe pour ce restream.

    - Si elle existe : la retourne
    - Sinon :
        - construit le preset via preset_factory
        - construit la session runtime
        - sauvegarde
        - retourne la session
    """

    existing = load_session_restream(restream_id)
    if existing is not None:
        if existing.get("tracker_type") == tracker_type:
            return existing

        current_app.logger.info(
            "Tracker session type mismatch (restream_id=%s, got=%s, expected=%s) -> reset",
            restream_id,
            existing.get("tracker_type"),
            tracker_type,
        )

    # Création du preset par défaut (via le registry)
    preset = preset_factory(participants_count)

    session = build_session_from_preset(
        preset=preset,
        tracker_type=tracker_type,
        restream_id=restream_id,
        restream_slug=restream_slug,
    )

    save_session_restream(restream_id, session)
    return session

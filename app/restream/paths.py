# app/restream/paths.py
from pathlib import Path
from flask import current_app

def indices_sessions_dir() -> Path:
    return Path(current_app.instance_path) / "indices" / "sessions"

def indices_templates_dir() -> Path:
    return Path(current_app.instance_path) / "indices" / "templates"

def tracker_session_path_restream(restream_id: int) -> Path:
    return (
        Path(current_app.instance_path)
        / "trackers"
        / "sessions"
        / f"restream_{restream_id}.json"
    )

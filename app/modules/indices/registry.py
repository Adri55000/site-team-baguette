import json
from pathlib import Path
from flask import current_app


# ------------------------------------------------------------------
# Helpers internes
# ------------------------------------------------------------------

def _get_templates_dir() -> Path:
    return (
        Path(current_app.instance_path)
        / "indices"
        / "templates"
    )


def _iter_template_files():
    templates_dir = _get_templates_dir()

    if not templates_dir.exists():
        return []

    return sorted(templates_dir.glob("*.json"))


def _load_template_metadata(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    return {
        "key": path.stem,
        "label": data.get("label", path.stem),
    }


# ------------------------------------------------------------------
# API publique
# ------------------------------------------------------------------

def get_available_indices_templates():
    """
    Retourne la liste des templates d’indices disponibles,
    pour les <select> create / edit.

    Format:
    [
        { "key": "ssr-s4", "label": "SSR — Saison 4" },
        ...
    ]
    """
    templates = []

    for path in _iter_template_files():
        meta = _load_template_metadata(path)
        if meta:
            templates.append(meta)

    return templates


def is_valid_indices_template(template_key: str) -> bool:
    """
    Validation backend.
    'none' est toujours valide.
    """
    if template_key == "none":
        return True

    for tpl in get_available_indices_templates():
        if tpl["key"] == template_key:
            return True

    return False


def get_indices_template_path(template_key: str) -> Path:
    """
    Retourne le chemin du fichier template JSON.
    À appeler uniquement si template_key != 'none'.
    """
    if template_key == "none":
        raise ValueError("No template path for 'none'")

    path = _get_templates_dir() / f"{template_key}.json"

    if not path.exists():
        raise FileNotFoundError(f"Indices template not found: {template_key}")

    return path

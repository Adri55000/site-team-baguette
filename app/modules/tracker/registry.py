"""
Tracker registry

Rôle :
- décrire les trackers disponibles
- fournir leur définition complète
- centraliser catalog + preset par défaut + frontend assets

Le registry NE :
- crée PAS de session
- ne touche PAS au filesystem
- ne connaît PAS les routes
"""

from typing import Dict, Any


# ======================================================================
# SSR TRACKER — DÉFINITION SPÉCIFIQUE AU JEU
# ======================================================================

# 🔁 SPÉCIFIQUE SSR
from app.modules.tracker.games.ssr.catalog import get_catalog as ssr_get_catalog
from app.modules.tracker.games.ssr.preset import build_default_preset as ssr_default_preset


def _ssr_tracker_definition() -> Dict[str, Any]:
    """
    Définition complète du tracker SSR.
    TOUT ce qui est ici est spécifique au tracker SSR.
    """
    return {
        # --- identité ---
        "tracker_type": "ssr_inventory",
        "label": "SSR — Inventory",

        # --- backend ---
        "catalog": ssr_get_catalog,

        # preset par défaut (factory, PAS l’état final)
        "default_preset": ssr_default_preset,

        # --- frontend ---
        "frontend": {
            # bloc/template principal
            "template_block": "tracker/ssr_inventory/block.html",

            # assets
            "css": "css/tracker/tracker_ssr.css",
            "js": "js/tracker/tracker_ssr.js",
        },
    }


# ======================================================================
# REGISTRY CENTRAL
# ======================================================================

# ✅ GÉNÉRIQUE (ne dépend d’aucun jeu)
_TRACKER_REGISTRY: Dict[str, callable] = {
    "ssr_inventory": _ssr_tracker_definition,
    # futurs trackers :
    # "ootr_inventory": _ootr_tracker_definition,
}


# ======================================================================
# API PUBLIQUE
# ======================================================================

# ✅ GÉNÉRIQUE
def get_tracker_definition(tracker_type: str) -> Dict[str, Any]:
    """
    Retourne la définition complète d’un tracker.

    Lève KeyError si le tracker n’existe pas.
    """
    if tracker_type not in _TRACKER_REGISTRY:
        raise KeyError(f"Unknown tracker type: {tracker_type}")

    return _TRACKER_REGISTRY[tracker_type]()


# ✅ GÉNÉRIQUE
def is_valid_tracker_type(tracker_type: str) -> bool:
    """
    Validation backend.
    'none' est toujours valide.
    """
    return tracker_type == "none" or tracker_type in _TRACKER_REGISTRY


# ✅ GÉNÉRIQUE
def get_available_trackers():
    """
    Liste des trackers disponibles pour les <select> create / edit.
    """
    trackers = []

    for tracker_type, factory in _TRACKER_REGISTRY.items():
        definition = factory()
        trackers.append({
            "key": tracker_type,
            "label": definition["label"],
        })

    return trackers

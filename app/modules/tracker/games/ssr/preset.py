"""
Preset par défaut pour le tracker SSR.

Responsabilité :
- générer l’état initial d’une session tracker
- sans effet de bord
- sans accès DB / filesystem
- sans dépendance aux routes
"""

from typing import Dict, Any, List
from app.modules.tracker.games.ssr.catalog import get_catalog


def _build_empty_item_state(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Génère l’état initial d’un item du catalog SSR.
    """
    item_type = item.get("type")

    # Toggle simple (épée, bottes, etc.)
    if item_type == "toggle":
        return {"value": 0}

    # Cycle (ex: épée évolutive)
    if item_type == "cycle":
        return {"value": 0}

    # Counter (ex: clés, fragments)
    if item_type == "counter":
        return {"value": item.get("min", 0)}

    # Wallet / capacité
    if item_type == "wallet":
        return {"value": item.get("levels", [0])[0]}

    # Composite (overlay conditionnel)
    if item_type == "composite":
        return {"active": False}

    # Fallback (sécurité)
    return {"value": 0}


def _build_participant_state(catalog: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construit l'état initial d'un participant SSR.
    - items : valeurs scalaires compatibles macro (int / bool)
    - dungeons / tablets / triforces : structure SSR historique
    """

    items: Dict[str, Any] = {}

    for it in catalog.get("items", []):
        item_id = it["id"]

        # Si le catalog définit des niveaux explicites, on prend le niveau initial
        if it.get("level_values"):
            items[item_id] = it["level_values"][0]
        else:
            items[item_id] = 0

    return {
        "gomode": 0,
        "items": items,
        "wallet_bonus": 0,
        "dungeons": {
            "SV": 0, "ET": 0, "LMF": 0, "AC": 0, "SSH": 0, "FS": 0, "SK": 0
        },
        "tablets": {"emerald": False, "ruby": False, "amber": False},
        "triforces": {"wisdom": False, "power": False, "courage": False},
    }


def build_default_preset(participants_count: int = 1) -> Dict[str, Any]:
    """
    Factory du preset par défaut SSR.

    Retourne un dict prêt à être injecté dans une session tracker.
    """
    catalog = get_catalog()

    participants: List[Dict[str, Any]] = []

    for _ in range(participants_count):
        participants.append(
            _build_participant_state(catalog)
        )

    return {
        "participants": participants,
    }

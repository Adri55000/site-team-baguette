import json
import re
from flask import abort

def get_tournament_phases(db, tournament_id):
    rows = db.execute(
        """
        SELECT id, name, type, position, details
        FROM tournament_phases
        WHERE tournament_id = ?
        ORDER BY position ASC
        """,
        (tournament_id,)
    ).fetchall()

    phases = []

    for r in rows:
        # Parsing sûr du JSON details
        details_obj = {}
        raw_details = r["details"] if "details" in r.keys() else None

        if raw_details:
            try:
                parsed = json.loads(raw_details)
                if isinstance(parsed, dict):
                    details_obj = parsed
            except Exception:
                details_obj = {}

        # Champ dérivé : qualifiers_per_group
        qualifiers_per_group = None
        if details_obj.get("qualifiers_per_group") is not None:
            try:
                qualifiers_per_group = int(details_obj["qualifiers_per_group"])
            except (ValueError, TypeError):
                qualifiers_per_group = None

        # On renvoie un dict enrichi
        phase = dict(r)
        phase["details_obj"] = details_obj
        phase["qualifiers_per_group"] = qualifiers_per_group

        phases.append(phase)

    return phases


def is_reserved_casual_prefix(title: str) -> bool:
    """
    Returns True if the tournament title uses the reserved [CASUAL] prefix.
    This prefix is reserved for system-created casual tournaments.
    """
    if not title:
        return False

    return title.strip().upper().startswith("[CASUAL")

def is_casual_tournament(name: str) -> bool:
    return bool(name) and name.strip().upper().startswith("[CASUAL")


def ensure_public_tournament(tournament):
    if not tournament:
        return  # important pour laisser le fallback external
    if tournament["name"] and tournament["name"].strip().upper().startswith("[CASUAL"):
        abort(404)


CASUAL_PREFIX_RE = re.compile(r"^\s*\[CASUAL[^\]]*\]\s*", re.IGNORECASE)

def overlay_tournament_name(name: str) -> str:
    """
    Tournament name for OBS overlays: removes [CASUAL...] prefix if present.
    Keeps the rest unchanged.
    """
    if not name:
        return ""
    return CASUAL_PREFIX_RE.sub("", name).strip()


###########################################
### pour les noms trop long
###########################################


# 1) mapping exact (le plus sûr)
OVERLAY_NAME_ALIASES = {
    "Pacmanpowerghost": "Pacman",
    "Fireworkspinner": "Firework",
    "YourAverageLink": "YAL",
}

# 2) mapping "contient" (exemple au cas où)
OVERLAY_NAME_CONTAINS = [
    # (pattern, replacement)
    (re.compile(r"Team Baguette Ultimate", re.IGNORECASE), "TB Ultimate"),
]

def overlay_player_name(name: str) -> str:
    """
    Return a player name formatted for OBS overlays.
    - Exact alias mapping first
    - Then 'contains' replacements
    - Fallback to original
    """
    if not name:
        return ""

    n = name.strip()

    # exact match first (most predictable)
    if n in OVERLAY_NAME_ALIASES:
        return OVERLAY_NAME_ALIASES[n]

    # optional: contains rules
    for rx, repl in OVERLAY_NAME_CONTAINS:
        if rx.search(n):
            return rx.sub(repl, n)

    return n
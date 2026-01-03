import json

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

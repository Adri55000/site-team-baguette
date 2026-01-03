def display_team_name(team):
    """
    Affiche un nom d’équipe lisible.
    Supprime le préfixe 'Solo - ' si présent.
    Accepte :
    - string
    - sqlite3.Row
    - dict
    - objet avec attribut .name
    """

    if not team:
        return ""

    # CAS 1 : string directe
    if isinstance(team, str):
        name = team

    # CAS 2 : dict ou sqlite Row
    elif isinstance(team, dict):
        name = team.get("name", "")

    # CAS 3 : objet
    else:
        name = getattr(team, "name", "")

    if name.startswith("Solo - "):
        return name[7:]

    return name

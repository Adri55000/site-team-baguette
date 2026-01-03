ROLE_HIERARCHY = {
    "invité": 0,
    "éditeur": 1,
    "restreamer": 2,
    "admin": 3,
}

def is_valid_role(role):
    return role in ROLE_HIERARCHY

def has_required_role(user_role, required_role):
    return ROLE_HIERARCHY.get(user_role, -1) >= ROLE_HIERARCHY.get(required_role, 0)

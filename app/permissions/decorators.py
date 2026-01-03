from functools import wraps
from flask import abort
from flask_login import current_user

from app.permissions.roles import has_required_role, is_valid_role

def role_required(min_role):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)

            user_role = getattr(current_user, "role", None)
            if not is_valid_role(user_role):
                abort(403)

            if not has_required_role(user_role, min_role):
                abort(403)

            return f(*args, **kwargs)
        return wrapped
    return decorator

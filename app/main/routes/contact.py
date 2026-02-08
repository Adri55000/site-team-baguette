from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app, make_response
from flask_babel import gettext as _
from flask_login import current_user
from app.database import get_db
from app.auth.utils import login_required
from werkzeug.security import check_password_hash, generate_password_hash
import json
import math
from app.modules.tournaments import ensure_public_tournament
from collections import defaultdict
from flask_babel import get_locale as babel_get_locale
from app.modules.i18n import get_translation

@main_bp.get("/contact")
def contact():
    return render_template(
        "pages/contact.html",
        discord_invite_url=current_app.config.get("DISCORD_INVITE_URL", ""),
        discord_server_name=current_app.config.get("DISCORD_SERVER_NAME", "notre Discord"),
        contact_email=current_app.config.get("CONTACT_EMAIL", ""),
    )
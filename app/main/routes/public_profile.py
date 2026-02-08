from flask import render_template, redirect, url_for, flash
from flask_babel import gettext as _
from app.database import get_db
import json
from app.main import main_bp

@main_bp.route("/user/<int:user_id>")
def public_profile(user_id):
    db = get_db()
    user = db.execute(
        """
        SELECT username, role, created_at,
               avatar_filename, description, social_links
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()

    if not user:
        flash(_("Utilisateur introuvable."), "error")
        return redirect(url_for("main.home"))

    links = json.loads(user["social_links"]) if user["social_links"] else {}

    return render_template("main/public_profile.html", user=dict(user), links=links)

@main_bp.route("/u/<username>")
def public_profile_by_name(username):
    db = get_db()
    user = db.execute(
        "SELECT id FROM users WHERE username = ?",
        (username,)
    ).fetchone()

    if not user:
        flash(_("Utilisateur introuvable."), "error")
        return redirect(url_for("main.home"))

    return redirect(url_for("main.public_profile", user_id=user["id"]))

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_babel import gettext as _
from flask_login import current_user
from app.database import get_db
from app.auth.utils import login_required
import json
from . import main_bp


@main_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    db = get_db()

    if request.method == "POST":
        description = request.form.get("description", "").strip()

        links = {
            "racetime": request.form.get("link_racetime", "").strip(),
            "twitch": request.form.get("link_twitch", "").strip(),
            "youtube": request.form.get("link_youtube", "").strip(),
            "discord": request.form.get("discord_handle", "").strip(),
        }

        links = {k: v for k, v in links.items() if v}
        links_json = json.dumps(links)

        db.execute(
            """
            UPDATE users
            SET description = ?, social_links = ?
            WHERE id = ?
            """,
            (description, links_json, current_user.id)
        )
        db.commit()

        flash(_("Profil mis à jour !"), "success")
        return redirect(url_for("main.profile"))

    user = db.execute(
        """
        SELECT username, role, created_at, last_login,
               avatar_filename, description, social_links
        FROM users WHERE id = ?
        """,
        (current_user.id,)
    ).fetchone()

    links = json.loads(user["social_links"]) if user["social_links"] else {}

    return render_template("main/profile.html", user=dict(user), links=links, user_id=current_user.id)

@main_bp.route("/profile/password", methods=["GET", "POST"])
@login_required
def change_password():
    db = get_db()

    if request.method == "POST":
        old_password = request.form.get("old_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        row = db.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (current_user.id,)
        ).fetchone()

        errors = []
        if not row:
            abort(403)

        if not check_password_hash(row["password_hash"], old_password):
            errors.append("L'ancien mot de passe est incorrect.")

        if len(new_password) < 6:
            errors.append("Le nouveau mot de passe doit faire au moins 6 caractères.")

        if new_password != confirm_password:
            errors.append("La confirmation ne correspond pas.")

        if errors:
            return render_template(
                "main/change_password.html",
                errors=errors
            )


        new_hash = generate_password_hash(new_password)

        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_hash, current_user.id)
        )
        db.commit()

        flash(_("Mot de passe mis à jour avec succès !"), "success")
        return redirect(url_for("main.profile"))

    return render_template("main/change_password.html")
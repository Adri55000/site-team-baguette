import os
import secrets
import string

from flask import (
    request,
    render_template,
    redirect,
    url_for,
    flash,
    abort,
    current_app,
)
from app.auth.utils import login_required
from werkzeug.security import generate_password_hash

from .. import admin_bp
from app.database import get_db
from app.permissions.decorators import role_required
from app.permissions.roles import is_valid_role
from flask_babel import _



@admin_bp.route("/users")
@login_required
@role_required("admin")
def users_list():
    page = int(request.args.get("page", 1))
    per_page = 20
    offset = (page - 1) * per_page

    q = request.args.get("q", "").strip()
    role = request.args.get("role", "")

    where = []
    params = []

    if q:
        where.append("username LIKE ?")
        params.append(f"%{q}%")

    if role:
        where.append("role = ?")
        params.append(role)

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    conn = get_db()

    users = conn.execute(f"""
        SELECT id, username, role, avatar_filename, created_at, is_active
        FROM users
        {where_sql}
        ORDER BY username ASC
        LIMIT ? OFFSET ?
    """, (*params, per_page, offset)).fetchall()

    total = conn.execute(
        f"SELECT COUNT(*) FROM users {where_sql}",
        params
    ).fetchone()[0]

    total_pages = (total + per_page - 1) // per_page

    return render_template(
        "admin/users_list.html",
        users=users,
        page=page,
        total_pages=total_pages,
        search=q,
        role=role
    )




# --- Formulaire d’édition ---
@admin_bp.route("/users/edit/<int:user_id>")
@login_required
@role_required("admin")
def edit_user(user_id):
    db = get_db()
    user = db.execute("""
        SELECT id, username, role, is_active, avatar_filename
        FROM users
        WHERE id = ?
    """, (user_id,)).fetchone()

    if not user:
        flash(_("Utilisateur introuvable."), "error")
        return redirect(url_for("admin.users_list"))

    return render_template("admin/edit_user.html", user=user)


# --- Validation de l’édition ---
@admin_bp.route("/users/edit/<int:user_id>", methods=["POST"])
@login_required
@role_required("admin")
def edit_user_post(user_id):
    new_role = request.form.get("role")
    if not is_valid_role(new_role):
        flash(_("Rôle invalide."), "error")
        abort(400)
    active = 1 if request.form.get("is_active") == "on" else 0

    db = get_db()
    db.execute("""
        UPDATE users
        SET role = ?, is_active = ?
        WHERE id = ?
    """, (new_role, active, user_id))
    db.commit()

    flash(_("Modifications enregistrées."), "success")
    return redirect(url_for("admin.users_list"))

@admin_bp.route("/users/<int:user_id>/reset_avatar", methods=["POST"])
@login_required
@role_required("admin")
def reset_avatar(user_id):
    db = get_db()

    # Récupérer l’avatar actuel
    user = db.execute(
        "SELECT avatar_filename FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    if not user:
        flash(_("Utilisateur introuvable."), "error")
        return redirect(url_for("admin.users_list"))

    # Supprimer le fichier s’il existe
    if user["avatar_filename"]:
        path = os.path.join(
            current_app.static_folder,
            "avatars",
            user["avatar_filename"]
        )
        if os.path.exists(path):
            os.remove(path)

    # Reset en BDD
    db.execute(
        "UPDATE users SET avatar_filename = NULL WHERE id = ?",
        (user_id,)
    )
    db.commit()

    flash(_("Avatar réinitialisé."), "success")
    return redirect(url_for("admin.edit_user", user_id=user_id))

@admin_bp.route("/users/<int:user_id>/reset_password", methods=["POST"])
@login_required
@role_required("admin")
def reset_password(user_id):
    db = get_db()

    # Nouveau mot de passe temporaire (à ajuster si besoin)
    alphabet = string.ascii_letters + string.digits
    new_password = ''.join(secrets.choice(alphabet) for _ in range(10))
    hashed = generate_password_hash(new_password)

    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hashed, user_id)
    )
    db.commit()

    flash(_("Mot de passe temporaire généré : %(pswd)s — l’utilisateur devra le changer à la prochaine connexion.", pswd=new_password),
    "warning"
    )

    return redirect(url_for("admin.edit_user", user_id=user_id))

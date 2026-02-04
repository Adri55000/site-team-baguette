from flask import render_template, request, redirect, flash, url_for, current_app
from flask_babel import gettext as _
from . import auth_bp
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from app.database import get_db
from PIL import Image
import io
import os
from flask_login import login_user, logout_user, current_user
from app.auth.models import User
from app.auth.utils import login_required
import sqlite3

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    db = get_db()
    cursor = db.cursor()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        
        # Règle métier : tout nouvel utilisateur est invité
        role = "invité"

        # Validation
        errors = []

        if not username:
            errors.append(_("Le nom d'utilisateur est obligatoire."))
        elif len(username) > 30:
            errors.append(_("Le nom d'utilisateur ne doit pas dépasser 30 caractères."))

        if len(password) < 6:
            errors.append(_("Le mot de passe doit contenir au moins 6 caractères."))

        if errors:
            return render_template(
                "auth/register.html",
                errors=errors,
                username=username
            )


        password_hash = generate_password_hash(password)
        created_at = datetime.now().isoformat()

        try:
            cursor.execute(
                """
                INSERT INTO users (username, password_hash, role, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (username, password_hash, role, created_at)
            )
            db.commit()

            flash(_("Compte créé avec succès ! Vous pouvez maintenant vous connecter."), "success")
            return redirect(url_for("auth.login"))
            
        except sqlite3.IntegrityError:
            return render_template(
                "auth/register.html",
                errors=[_("Nom d'utilisateur déjà utilisé.")],
                username=username
            )


    return render_template("auth/register.html")




@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    db = get_db()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash(_("Nom d'utilisateur et mot de passe obligatoires."), "error")
            return redirect(url_for("auth.login"))

        row = db.execute("""
        SELECT
            id,
            username,
            password_hash,
            role,
            is_active,
            avatar_filename,
            created_at,
            last_login
            FROM users
        WHERE username = ?
        """, (username,)).fetchone()

        if row and check_password_hash(row["password_hash"], password):
            user = User(row)
            
            if not user.is_active:
                flash(_("Votre compte a été désactivé."), "error")
                return redirect(url_for("auth.login"))
            
            login_user(user)

            db.execute(
                "UPDATE users SET last_login = ? WHERE id = ?",
                (datetime.now().isoformat(), row["id"])
            )
            db.commit()
            

            flash(_("Connecté en tant que %(name)s", name=user.username), "success")
            return redirect(url_for("main.home"))

        flash(_("Nom d'utilisateur ou mot de passe incorrect"), "error")
        return redirect(url_for("auth.login"))

    return render_template("auth/login.html")



@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash(_("Vous êtes déconnecté."), "info")
    return redirect(url_for("main.home"))





@auth_bp.route("/upload_avatar", methods=["POST"])
@login_required
def upload_avatar():

    file = request.files.get("avatar")
    if not file:
        flash(_("Aucun fichier sélectionné."), "error")
        return redirect(url_for("main.profile"))

    # Vérifier extension
    allowed = {"png", "jpg", "jpeg"}
    ext = file.filename.rsplit(".", 1)[-1].lower()

    if ext not in allowed:
        flash(_("Format d'image non supporté (PNG, JPG, JPEG)."), "error")
        return redirect(url_for("main.profile"))

    # Charger l'image en mémoire
    try:
        img = Image.open(file)
    except Exception:
        flash(_("Fichier image invalide ou corrompu."), "error")
        return redirect(url_for("main.profile"))

    # Vérifier dimensions maximales
    if img.width > 3000 or img.height > 3000:
        flash(_("L'image est trop grande (max 3000x3000 pixels)."), "error")
        return redirect(url_for("main.profile"))

    # Conversion RGB si nécessaire
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    # Crop carré centré
    width, height = img.size
    min_side = min(width, height)
    left = (width - min_side) // 2
    top = (height - min_side) // 2
    right = left + min_side
    bottom = top + min_side
    img = img.crop((left, top, right, bottom))

    # Resize en 256x256
    img = img.resize((256, 256), Image.LANCZOS)

    # Nom de fichier basé sur l'utilisateur courant
    filename = f"user_{current_user.id}.png"
    save_path = os.path.join(
        current_app.root_path, "static", "avatars", filename
    )

    # Sauvegarde propre
    img.save(save_path, format="PNG", optimize=True)

    # Mise à jour DB
    db = get_db()
    db.execute(
        "UPDATE users SET avatar_filename = ? WHERE id = ?",
        (filename, current_user.id)
    )
    db.commit()

    flash(_("Avatar mis à jour avec succès !"), "success")
    return redirect(url_for("main.profile"))

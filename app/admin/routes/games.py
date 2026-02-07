from datetime import datetime

from flask import (
    request,
    render_template,
    redirect,
    url_for,
    flash,
)
from flask_login import login_required
from flask_babel import _

from .. import admin_bp
from app.database import get_db
from app.permissions.decorators import role_required
from app.modules.text import slugify

@admin_bp.route("/games")
@login_required
@role_required("admin")   # uniquement admin pour le moment
def games_list():
    db = get_db()
    games = db.execute(
        "SELECT id, name, short_name, icon_path, color FROM games ORDER BY name"
    ).fetchall()
    return render_template("admin/games.html", games=games)


@admin_bp.route("/games/add", methods=["POST"])
@login_required
@role_required("admin")
def games_add():
    name = request.form.get("name", "").strip()
    short_name = request.form.get("short_name", "").strip()
    color = request.form.get("color", "").strip() or None

    if not name or not short_name:
        flash(_("Nom et abréviation obligatoires."), "error")
        return redirect(url_for("admin.games_list"))

    db = get_db()

    # 1) Création du jeu
    db.execute(
        """
        INSERT INTO games (name, short_name, color)
        VALUES (?, ?, ?)
        """,
        (name, short_name, color)
    )

    # Récupère l'id du jeu fraîchement créé (SQLite)
    game_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    # 2) Auto-création du tournoi CASUAL associé
    game_slug = slugify(name)  # ou slugify(short_name) si vous préférez un slug plus stable
    casual_tournament_name = f"[CASUAL] {name}"
    casual_tournament_slug = f"casual-{game_slug}"

    existing = db.execute(
        """
        SELECT id
        FROM tournaments
        WHERE game_id = ? AND slug = ?
        """,
        (game_id, casual_tournament_slug)
    ).fetchone()

    if not existing:
        db.execute(
            """
            INSERT INTO tournaments
                (name, slug, game_id, status, source, metadata, created_at)
            VALUES (?, ?, ?, ?, 'internal', ?, ?)
            """,
            (
                casual_tournament_name,
                casual_tournament_slug,
                game_id,
                "draft",          # ou "active" si tu veux qu'il soit immédiatement utilisable
                "",               # metadata
                datetime.now().isoformat(),
            )
        )

    db.commit()

    flash(_("Jeu ajouté avec succès."), "success")
    return redirect(url_for("admin.games_list"))


@admin_bp.route("/games/delete/<int:game_id>", methods=["POST"])
@login_required
@role_required("admin")
def games_delete(game_id):
    db = get_db()

    # Empêcher la suppression d'un jeu utilisé
    ref = db.execute("SELECT 1 FROM tournaments WHERE game_id = ?", (game_id,)).fetchone()
    if ref:
        flash(_("Impossible de supprimer ce jeu : il est utilisé par un tournoi."), "error")
        return redirect(url_for("admin.games_list"))

    db.execute("DELETE FROM games WHERE id = ?", (game_id,))
    db.commit()

    flash(_("Jeu supprimé."), "success")
    return redirect(url_for("admin.games_list"))

@admin_bp.route("/games/edit/<int:game_id>")
@login_required
@role_required("admin")
def game_edit(game_id):
    db = get_db()
    game = db.execute(
        "SELECT * FROM games WHERE id = ?",
        (game_id,)
    ).fetchone()

    if not game:
        flash(_("Jeu introuvable."), "error")
        return redirect(url_for("admin.games_list"))

    return render_template("admin/edit_game.html", game=game)

@admin_bp.route("/games/edit/<int:game_id>", methods=["POST"])
@login_required
@role_required("admin")
def game_edit_post(game_id):
    full_name = request.form.get("full_name", "").strip()
    short_name = request.form.get("short_name", "").strip()
    color = request.form.get("color", "").strip()

    db = get_db()
    db.execute(
        "UPDATE games SET name = ?, short_name = ?, color = ? WHERE id = ?",
        (full_name, short_name, color or None, game_id)
    )
    db.commit()

    flash(_("Jeu modifié avec succès."), "success")
    return redirect(url_for("admin.games_list"))
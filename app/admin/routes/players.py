from flask import (
    request,
    render_template,
    redirect,
    url_for,
    flash,
    abort,
)
from flask_login import login_required
from flask_babel import _

from .. import admin_bp
from app.database import get_db
from app.permissions.decorators import role_required
from app.admin.domain import can_delete_player


@admin_bp.route("/players")
@login_required
@role_required("admin")
def players_list():
    page = int(request.args.get("page", 1))
    per_page = 20
    offset = (page - 1) * per_page

    q = request.args.get("q", "").strip()

    conn = get_db()

    where = ""
    params = []

    if q:
        where = "WHERE name LIKE ?"
        params.append(f"%{q}%")

    players = conn.execute(f"""
        SELECT id, name, created_at, racetime_user
        FROM players
        {where}
        ORDER BY name ASC
        LIMIT ? OFFSET ?
    """, (*params, per_page, offset)).fetchall()

    total = conn.execute(
        f"SELECT COUNT(*) FROM players {where}",
        params
    ).fetchone()[0]

    total_pages = (total + per_page - 1) // per_page

    return render_template(
        "admin/players_list.html",
        players=players,
        page=page,
        total_pages=total_pages,
        search=q
    )




@admin_bp.route("/players/new", methods=["GET", "POST"])
@login_required
@role_required("admin")
def players_create():
    if request.method == "POST":
        name = request.form["name"].strip()
        racetime_user_raw = request.form.get("racetime_user", "").strip()
        racetime_user = racetime_user_raw or None

        if name:
            conn = get_db()
            conn.execute(
                """
                INSERT INTO players (name, racetime_user)
                VALUES (?, ?)
                """,
                (name, racetime_user)
            )
            conn.commit()
            flash(_("Joueur créé avec succès."), "success")
            return redirect(url_for("admin.players_list"))

    return render_template("admin/players_form.html")


@admin_bp.route("/players/<int:player_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def players_edit(player_id):
    conn = get_db()

    # 1️⃣ Récupérer le joueur
    player = conn.execute(
        "SELECT * FROM players WHERE id = ?",
        (player_id,)
    ).fetchone()

    if not player:
        abort(404)

    # 2️⃣ Traitement du formulaire (édition)
    if request.method == "POST":
        name = request.form["name"].strip()
        racetime_user_raw = request.form.get("racetime_user", "").strip()
        racetime_user = racetime_user_raw or None

        if name:
            conn.execute(
                """
                UPDATE players
                SET name = ?, racetime_user = ?
                WHERE id = ?
                """,
                (name, racetime_user, player_id)
            )
            conn.commit()
            return redirect(url_for("admin.players_list"))

    # 3️⃣ Calcul de can_delete (MÊME logique que players_delete)
    can_delete, _ = can_delete_player(conn, player_id)

    # 4️⃣ Rendu
    return render_template(
        "admin/players_form.html",
        player=player,
        can_delete=can_delete
    )



@admin_bp.route("/players/<int:player_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def players_delete(player_id):
    conn = get_db()

    # 1️⃣ Le joueur existe ?
    player = conn.execute(
        "SELECT id FROM players WHERE id = ?",
        (player_id,)
    ).fetchone()

    if not player:
        abort(404)

    allowed, reason = can_delete_player(conn, player_id)

    if not allowed:
        flash(reason, "error")
        abort(400)

    # 5️⃣ Suppression propre
    # - liens joueur ↔ équipes
    # - équipe solo devenue vide
    # - joueur

    conn.execute(
        "DELETE FROM team_players WHERE player_id = ?",
        (player_id,)
    )

    # Supprimer les équipes vides (typiquement l’équipe solo)
    conn.execute("""
        DELETE FROM teams
        WHERE id NOT IN (
            SELECT DISTINCT team_id FROM team_players
        )
    """)

    conn.execute(
        "DELETE FROM players WHERE id = ?",
        (player_id,)
    )

    conn.commit()
    flash(_("Joueur supprimé."), "success")

    return redirect(url_for("admin.players_list"))
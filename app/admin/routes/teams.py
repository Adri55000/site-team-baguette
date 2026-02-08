from flask import (
    request,
    render_template,
    redirect,
    url_for,
    flash,
    abort,
)
from app.auth.utils import login_required
from flask_babel import _

from .. import admin_bp
from app.database import get_db
from app.permissions.decorators import role_required
from app.admin.domain import can_delete_team


@admin_bp.route("/teams")
@login_required
@role_required("admin")
def teams_list():
    page = int(request.args.get("page", 1))
    per_page = 20
    offset = (page - 1) * per_page
    q = request.args.get("q", "").strip()

    conn = get_db()

    params = []
    where = ""

    if q:
        where = "WHERE t.name LIKE ?"
        params.append(f"%{q}%")

    # Équipes multi-joueurs uniquement + noms des joueurs
    teams = conn.execute(f"""
        SELECT
            t.id,
            t.name,
            COUNT(tp.player_id) AS size,
            GROUP_CONCAT(p.name, ', ') AS players
        FROM teams t
        JOIN team_players tp ON tp.team_id = t.id
        JOIN players p ON p.id = tp.player_id
        {where}
        GROUP BY t.id
        HAVING size > 1
        ORDER BY t.name ASC
        LIMIT ? OFFSET ?
    """, (*params, per_page, offset)).fetchall()

    # Total pour la pagination
    total = conn.execute(f"""
        SELECT COUNT(*) FROM (
            SELECT t.id
            FROM teams t
            JOIN team_players tp ON tp.team_id = t.id
            {where}
            GROUP BY t.id
            HAVING COUNT(tp.player_id) > 1
        )
    """, params).fetchone()[0]

    total_pages = (total + per_page - 1) // per_page

    return render_template(
        "admin/teams_list.html",
        teams=teams,
        page=page,
        total_pages=total_pages,
        search=q
    )


@admin_bp.route("/teams/new", methods=["GET", "POST"])
@login_required
@role_required("admin")
def teams_create():
    conn = get_db()

    players = conn.execute("""
        SELECT id, name FROM players ORDER BY name
    """).fetchall()

    if request.method == "POST":
        name = request.form["name"].strip()
        member_ids = request.form.getlist("players")

        if name and len(member_ids) >= 2:
            cur = conn.execute(
                "INSERT INTO teams (name) VALUES (?)",
                (name,)
            )
            team_id = cur.lastrowid

            for pid in member_ids:
                conn.execute(
                    "INSERT INTO team_players (team_id, player_id) VALUES (?, ?)",
                    (team_id, pid)
                )

            conn.commit()
            flash(_("Équipe créée avec succès."), "success")

            return redirect(url_for("admin.teams_list"))

    return render_template(
        "admin/teams_form.html",
        players=players
    )

@admin_bp.route("/teams/<int:team_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def teams_delete(team_id):
    conn = get_db()

    allowed, reason = can_delete_team(conn, team_id)

    if not allowed:
        flash(reason, "error")
        abort(400)

    conn.execute("DELETE FROM team_players WHERE team_id = ?", (team_id,))
    conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
    conn.commit()
    flash(_("Équipe supprimée."), "success")

    return redirect(url_for("admin.teams_list"))

@admin_bp.route("/teams/<int:team_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def teams_edit(team_id):
    conn = get_db()

    # Équipe
    team = conn.execute(
        "SELECT * FROM teams WHERE id = ?",
        (team_id,)
    ).fetchone()

    if not team:
        abort(404)

    # Joueurs existants
    players = conn.execute("""
        SELECT id, name
        FROM players
        ORDER BY name
    """).fetchall()

    # Joueurs actuellement dans l’équipe
    current_players = conn.execute("""
        SELECT player_id
        FROM team_players
        WHERE team_id = ?
    """, (team_id,)).fetchall()
    current_ids = {p["player_id"] for p in current_players}

    # POST : mise à jour
    if request.method == "POST":
        name = request.form["name"].strip()
        member_ids = request.form.getlist("players")

        if name and len(member_ids) >= 2:
            conn.execute(
                "UPDATE teams SET name = ? WHERE id = ?",
                (name, team_id)
            )

            # reset membres
            conn.execute(
                "DELETE FROM team_players WHERE team_id = ?",
                (team_id,)
            )

            for pid in member_ids:
                conn.execute(
                    "INSERT INTO team_players (team_id, player_id) VALUES (?, ?)",
                    (team_id, pid)
                )

            conn.commit()
            return redirect(url_for("admin.teams_list"))

    can_delete, _ = can_delete_team(conn, team_id)

    return render_template(
        "admin/teams_form.html",
        team=team,
        players=players,
        current_ids=current_ids,
        can_delete=can_delete
    )
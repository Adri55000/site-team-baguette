from datetime import datetime

from flask import (
    request,
    render_template,
    redirect,
    url_for,
    flash,
    abort,
)
from app.auth.utils import login_required
from flask_babel import _, get_locale as babel_get_locale

from .. import admin_bp
from app.database import get_db
from app.permissions.decorators import role_required

from app.modules.text import slugify, normalize_group_name
from app.modules.i18n import get_translation
from app.modules.tournaments import get_tournament_phases, is_reserved_casual_prefix

@admin_bp.route("/tournaments")
@login_required
@role_required("admin")
def tournaments_list():
    db = get_db()

    # paramètres
    page = request.args.get("page", 1, type=int)
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()

    per_page = 10
    offset = (page - 1) * per_page

    # filtres
    where = []
    params = []

    if search:
        where.append("t.name LIKE ?")
        params.append(f"%{search}%")

    if status:
        where.append("t.status = ?")
        params.append(status)

    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    # total
    total = db.execute(
        f"""
        SELECT COUNT(*)
        FROM tournaments t
        {where_clause}
        """,
        params
    ).fetchone()[0]

    total_pages = max(1, (total + per_page - 1) // per_page)

    # liste
    tournaments = db.execute(
        f"""
        SELECT
            t.id,
            t.slug,
            t.name,
            t.status,
            t.source,
            t.created_at,
            g.name AS game_name,
            COUNT(tt.team_id) AS team_count
        FROM tournaments t
        LEFT JOIN games g ON g.id = t.game_id
        LEFT JOIN tournament_teams tt ON tt.tournament_id = t.id
        {where_clause}
        GROUP BY t.id
        ORDER BY t.created_at DESC
        LIMIT ? OFFSET ?
        """,
        (*params, per_page, offset)
    ).fetchall()

    lang = str(babel_get_locale() or "fr").strip().lower()

    tournaments = [dict(t) for t in tournaments]
    for t in tournaments:
        if t.get("slug"):
            tr = get_translation("tournament", t["slug"], "name", lang)
            if tr:
                t["name"] = tr

    return render_template(
        "admin/tournaments_list.html",
        tournaments=tournaments,
        page=page,
        total_pages=total_pages,
        search=search,
        status=status
    )

@admin_bp.route("/tournaments/create", methods=["GET", "POST"])
@login_required
@role_required("admin")
def tournaments_create():
    db = get_db()

    games = db.execute(
        "SELECT id, name FROM games ORDER BY name"
    ).fetchall()

    errors = {}

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        game_id = request.form.get("game_id")
        status = request.form.get("status", "draft")
        metadata = request.form.get("metadata", "").strip()

        if not name:
            errors["name"] = _("Le nom du tournoi est obligatoire.")
            
        if name and is_reserved_casual_prefix(name):
            errors["name"] = _("Le préfixe [CASUAL] est réservé aux tournois système.")

        if not game_id:
            errors["game_id"] = _("Un jeu doit être sélectionné.")

        if status not in ("draft", "active", "finished"):
            flash(_("Statut de tournoi invalide."), "error")
            abort(400)

        if not errors:
            slug = slugify(name)

            db.execute(
                """
                INSERT INTO tournaments
                    (name, slug, game_id, status, source, metadata, created_at)
                VALUES (?, ?, ?, ?, 'internal', ?, ?)
                """,
                (name, slug, game_id, status, metadata, datetime.now().isoformat())
            )
            db.commit()

            flash(_("Tournoi créé avec succès."), "success")
            return redirect(url_for("admin.tournaments_list"))

    return render_template(
        "admin/tournaments_form.html",
        tournament=None,
        games=games,
        errors=errors
    )


@admin_bp.route("/tournaments/<int:tournament_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_tournament_edit(tournament_id):
    db = get_db()

    tournament = db.execute(
        """
        SELECT id, name, game_id, status, source, metadata
        FROM tournaments
        WHERE id = ?
        """,
        (tournament_id,)
    ).fetchone()

    if not tournament:
        abort(404)

    games = db.execute(
        "SELECT id, name FROM games ORDER BY name"
    ).fetchall()

    # 🔹 Phases du tournoi (pour affichage & validation)
    phases = get_tournament_phases(db, tournament_id)

    errors = {}

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        game_id = request.form.get("game_id")
        status = request.form.get("status", tournament["status"])
        metadata = request.form.get("metadata", "").strip()

        if not name:
            errors["name"] = "Le nom du tournoi est obligatoire."
            
        if name and is_reserved_casual_prefix(name):
            errors["name"] = "Le préfixe [CASUAL] est réservé aux tournois système."

        if not game_id:
            errors["game_id"] = "Un jeu doit être sélectionné."

        if status not in ("draft", "active", "finished"):
            flash(_("Statut de tournoi invalide."), "error")
            abort(400)

        # 🔒 Règle métier existante
        if not errors :
            if tournament["status"] == "finished" and status != "finished":
                flash(
                    _("Un tournoi terminé ne peut pas être réactivé."),
                    "error"
                )
                return redirect(
                    url_for("admin.admin_tournament_edit", tournament_id=tournament_id)
                )

            # 🔒 NOUVELLE règle métier (Phase 6)
            if status == "active" and not phases:
                flash(
                    _("Impossible d'activer le tournoi : aucune phase n'est définie."),
                    "error"
                )
                return redirect(
                    url_for("admin.admin_tournament_edit", tournament_id=tournament_id)
                )

            db.execute(
                """
                UPDATE tournaments
                SET name = ?, game_id = ?, status = ?, metadata = ?
                WHERE id = ?
                """,
                (name, game_id, status, metadata, tournament_id)
            )
            db.commit()

            flash(_("Tournoi mis à jour."), "success")
            return redirect(url_for("admin.tournaments_list"))

    return render_template(
        "admin/tournaments_form.html",
        tournament=tournament,
        games=games,
        errors=errors,
        phases=phases  # 👈 prêt pour l’UX phases
    )


@admin_bp.route("/tournaments/<int:tournament_id>/teams")
@login_required
@role_required("admin")
def admin_tournament_teams(tournament_id):
    conn = get_db()

    # --- Tournoi ---
    tournament = conn.execute(
        "SELECT * FROM tournaments WHERE id = ?",
        (tournament_id,)
    ).fetchone()

    if not tournament:
        flash(_("Tournoi introuvable."), "error")
        return redirect(url_for("admin.tournaments_list"))

    # --- Pagination & filtres (PATTERN EXISTANT) ---
    page = int(request.args.get("page", 1))
    per_page = 20
    offset = (page - 1) * per_page

    q = request.args.get("q", "").strip()
    team_size = request.args.get("team_size", "all")

    # =====================================================
    # ÉQUIPES DÉJÀ INSCRITES (pas de pagination)
    # =====================================================
    registered_teams = conn.execute(
        """
        SELECT
            t.id,
            t.name,
            COUNT(tp.player_id) AS size,
            GROUP_CONCAT(p.name, ', ') AS players,
            tt.group_name,
            tt.seed,
            tt.position
        FROM tournament_teams tt
        JOIN teams t ON t.id = tt.team_id
        JOIN team_players tp ON tp.team_id = t.id
        JOIN players p ON p.id = tp.player_id
        WHERE tt.tournament_id = ?
        GROUP BY t.id
        ORDER BY t.name
        """,
        (tournament_id,)
    ).fetchall()
    
    # Récupère les groupes existants pour ce tournoi (pour dropdown/datalist)
    existing_groups = conn.execute(
        """
        SELECT DISTINCT group_name
        FROM tournament_teams
        WHERE tournament_id = ?
            AND group_name IS NOT NULL
            AND TRIM(group_name) != ''
        ORDER BY group_name COLLATE NOCASE
        """,
        (tournament_id,)
    ).fetchall()

    existing_groups = [row["group_name"] for row in existing_groups]

    # =====================================================
    # FILTRES équipes disponibles
    # =====================================================
    where = []
    params = [tournament_id]

    if q:
        where.append("t.name LIKE ?")
        params.append(f"%{q}%")

    having = []
    if team_size == "solo":
        having.append("COUNT(tp.player_id) = 1")
    elif team_size == "multi":
        having.append("COUNT(tp.player_id) >= 2")
    elif team_size.isdigit():
        having.append("COUNT(tp.player_id) = ?")
        params.append(int(team_size))

    where_sql = " AND " + " AND ".join(where) if where else ""
    having_sql = " HAVING " + " AND ".join(having) if having else ""

    # =====================================================
    # TOTAL équipes disponibles (pagination)
    # =====================================================
    total = conn.execute(
        f"""
        SELECT COUNT(*) FROM (
            SELECT t.id
            FROM teams t
            JOIN team_players tp ON tp.team_id = t.id
            LEFT JOIN tournament_teams tt
                ON tt.team_id = t.id
                AND tt.tournament_id = ?
            WHERE tt.team_id IS NULL
            {where_sql}
            GROUP BY t.id
            {having_sql}
        )
        """,
        params
    ).fetchone()[0]

    total_pages = (total + per_page - 1) // per_page

    # =====================================================
    # LISTE équipes disponibles
    # =====================================================
    available_teams = conn.execute(
        f"""
        SELECT
            t.id,
            t.name,
            COUNT(tp.player_id) AS size,
            GROUP_CONCAT(p.name, ', ') AS players
        FROM teams t
        JOIN team_players tp ON tp.team_id = t.id
        JOIN players p ON p.id = tp.player_id
        LEFT JOIN tournament_teams tt
            ON tt.team_id = t.id
            AND tt.tournament_id = ?
        WHERE tt.team_id IS NULL
        {where_sql}
        GROUP BY t.id
        {having_sql}
        ORDER BY t.name
        LIMIT ? OFFSET ?
        """,
        (*params, per_page, offset)
    ).fetchall()

    return render_template(
        "admin/tournaments/teams.html",
        tournament=tournament,
        registered_teams=registered_teams,
        existing_groups=existing_groups,
        available_teams=available_teams,
        page=page,
        total_pages=total_pages,
        search=q,
        team_size=team_size
    )


@admin_bp.route(
    "/tournaments/<int:tournament_id>/teams/add",
    methods=["POST"]
)
@login_required
@role_required("admin")
def admin_tournament_add_team(tournament_id):
    db = get_db()

    team_id = request.form.get("team_id", type=int)
    group_name = request.form.get("group_name")
    seed = request.form.get("seed", type=int)

    tournament = db.execute(
        "SELECT * FROM tournaments WHERE id = ?",
        (tournament_id,)
    ).fetchone()

    if tournament is None:
        flash(_("Tournoi introuvable."), "error")
        return redirect(url_for("admin.tournaments_list"))

    if tournament["status"] != "draft":
        flash(_("Impossible de modifier les équipes d’un tournoi actif ou terminé."), "error")
        return redirect(url_for("admin.admin_tournament_teams", tournament_id=tournament_id))

    team = db.execute(
        "SELECT id FROM teams WHERE id = ?",
        (team_id,)
    ).fetchone()

    if team is None:
        flash(_("Équipe introuvable."), "error")
        return redirect(url_for("admin.admin_tournament_teams", tournament_id=tournament_id))

    already = db.execute(
        """
        SELECT 1 FROM tournament_teams
        WHERE tournament_id = ? AND team_id = ?
        """,
        (tournament_id, team_id)
    ).fetchone()

    if already:
        flash(_("Cette équipe est déjà inscrite à ce tournoi."), "error")
        return redirect(url_for("admin.admin_tournament_teams", tournament_id=tournament_id))

    db.execute(
        """
        INSERT INTO tournament_teams (tournament_id, team_id, group_name, seed)
        VALUES (?, ?, ?, ?)
        """,
        (tournament_id, team_id, group_name, seed)
    )
    db.commit()

    flash(_("Équipe inscrite avec succès."), "success")
    return redirect(url_for("admin.admin_tournament_teams", tournament_id=tournament_id))

@admin_bp.route(
    "/tournaments/<int:tournament_id>/teams/remove/<int:team_id>",
    methods=["POST"]
)
@login_required
@role_required("admin")
def admin_tournament_remove_team(tournament_id, team_id):
    db = get_db()

    tournament = db.execute(
        "SELECT * FROM tournaments WHERE id = ?",
        (tournament_id,)
    ).fetchone()

    if tournament is None:
        flash(_("Tournoi introuvable."), "error")
        return redirect(url_for("admin.tournaments_list"))

    if tournament["status"] != "draft":
        flash(_("Impossible de modifier les équipes d’un tournoi actif ou terminé."), "error")
        return redirect(url_for("admin.admin_tournament_teams", tournament_id=tournament_id))

    db.execute(
        """
        DELETE FROM tournament_teams
        WHERE tournament_id = ? AND team_id = ?
        """,
        (tournament_id, team_id)
    )
    db.commit()

    flash(_("Équipe retirée du tournoi."), "success")
    return redirect(url_for("admin.admin_tournament_teams", tournament_id=tournament_id))
    

@admin_bp.route("/tournaments/<int:tournament_id>/teams/groups", methods=["POST"])
@login_required
@role_required("admin")
def admin_tournament_teams_update_groups(tournament_id):
    db = get_db()

    tournament = db.execute(
        "SELECT id, status FROM tournaments WHERE id = ?",
        (tournament_id,)
    ).fetchone()

    if not tournament:
        flash(_("Tournoi introuvable."), "error")
        return redirect(url_for("admin.admin_tournaments"))

    # v1: tu peux décider si c'est draft-only.
    # Je te mets draft-only par défaut (cohérent avec 'teams modifiables seulement en draft').
    if tournament["status"] != "draft":
        flash(_("Modification des groupes impossible : tournoi non en draft."), "warning")
        return redirect(url_for("admin.admin_tournament_teams", tournament_id=tournament_id))

    # Liste des groupes existants (pour normaliser vers un nom déjà connu)
    existing_groups = db.execute(
        """
        SELECT DISTINCT group_name
        FROM tournament_teams
        WHERE tournament_id = ?
          AND group_name IS NOT NULL
          AND TRIM(group_name) != ''
        """,
        (tournament_id,)
    ).fetchall()
    existing_groups = [row["group_name"] for row in existing_groups]

    # Récupère les équipes inscrites (pour savoir quoi traiter)
    teams = db.execute(
        "SELECT team_id FROM tournament_teams WHERE tournament_id = ?",
        (tournament_id,)
    ).fetchall()

    updated = 0

    for row in teams:
        team_id = row["team_id"]

        raw_group = request.form.get(f"group_name_{team_id}", "")
        group_name = normalize_group_name(raw_group, existing_groups)

        raw_pos = (request.form.get(f"position_{team_id}", "") or "").strip()
        if raw_pos == "":
            position = None
        else:
            try:
                position = int(raw_pos)
            except ValueError:
                flash(_("Position invalide pour l'équipe %(name)s.",name=team_id), "error")
                return redirect(url_for("admin.admin_tournament_teams", tournament_id=tournament_id))

        db.execute(
            """
            UPDATE tournament_teams
            SET group_name = ?, position = ?
            WHERE tournament_id = ? AND team_id = ?
            """,
            (group_name, position, tournament_id, team_id)
        )
        updated += 1

    db.commit()
    flash(_("Groupes enregistrés (%(name)s équipes).",name=updated), "success")
    return redirect(url_for("admin.admin_tournament_teams", tournament_id=tournament_id))
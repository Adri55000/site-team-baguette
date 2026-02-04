from flask import render_template, request, redirect, url_for, flash, current_app, abort, jsonify
from flask_babel import get_locale as babel_get_locale, gettext as _
from . import admin_bp
from app.database import get_db
from app.auth.utils import login_required
from app.permissions.decorators import role_required
from app.permissions.roles import is_valid_role
from app.admin.domain import can_delete_player, can_delete_team
from werkzeug.security import generate_password_hash
import os
from app.modules.text import slugify, _canonical_key, normalize_group_name
from datetime import datetime
from app.modules.tournaments import get_tournament_phases, is_reserved_casual_prefix
import secrets
import string
import json
from app.modules.tracker.registry import get_available_trackers, get_tracker_definition
from app.modules.tracker.presets import list_presets, create_preset, load_preset, save_preset, rename_preset, delete_preset
from app.modules.tracker.games.ssr.preset import build_default_preset as ssr_default_preset
from app.modules import racetime as racetime_mod
from app.modules.i18n import get_translation

@admin_bp.route("/")
@login_required
@role_required("admin")
def dashboard():
    return render_template("admin/dashboard.html")

# --- Liste des utilisateurs ---
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


@admin_bp.route("/matches")
@login_required
@role_required("admin")
def admin_matches():
    db = get_db()

    tournament_id = request.args.get("tournament_id", type=int)
    phase_id = request.args.get("phase_id", type=int)

    tournaments = db.execute(
        "SELECT id, name FROM tournaments ORDER BY created_at DESC"
    ).fetchall()

    if not tournament_id:
        return render_template(
            "admin/matches/index.html",
            tournaments=tournaments,
            selected_tournament=None,
            selected_phase_id=None
        )

    tournament = db.execute(
        "SELECT * FROM tournaments WHERE id = ?",
        (tournament_id,)
    ).fetchone()

    if not tournament:
        flash(_("Tournoi introuvable."), "error")
        return redirect(url_for("admin.admin_matches"))
        
    # ✅ Phases du tournoi (toutes, même si aucune série n'existe encore)
    phases = db.execute(
        """
        SELECT id, name, position, type
        FROM tournament_phases
        WHERE tournament_id = ?
        ORDER BY position
        """,
        (tournament_id,),
    ).fetchall()

    # ✅ Filtre optionnel sur la phase
    phase_filter_sql = ""
    params = [tournament_id]
    if phase_id:
        phase_filter_sql = " AND s.phase_id = ?"
        params.append(phase_id)        
        
    confrontations = db.execute(
        f"""
        SELECT
            s.id,
            s.phase_id,
            s.stage,
            s.best_of,
            s.winner_team_id,
            s.created_at,
            
            p.name AS phase_name,
            p.position AS phase_position,


            t1.name AS team1_name,
            t2.name AS team2_name,
            tw.name AS winner_name,

            -- Nombre total de matchs existants
            COUNT(DISTINCT m_all.id) AS match_count,
    
            -- Nombre de matchs terminés (joués)
            COUNT(DISTINCT m_done.id) AS matches_played,
    
            -- Victoires par équipe (pour le score BO)
            SUM(
                CASE
                    WHEN mt.team_id = s.team1_id AND mt.is_winner = 1 THEN 1
                    ELSE 0
                END
            ) AS team1_wins,
    
            SUM(
                CASE
                    WHEN mt.team_id = s.team2_id AND mt.is_winner = 1 THEN 1
                    ELSE 0
                END
            ) AS team2_wins

        FROM series s
        JOIN tournament_phases p ON p.id = s.phase_id
        LEFT JOIN teams t1 ON t1.id = s.team1_id
        LEFT JOIN teams t2 ON t2.id = s.team2_id
        LEFT JOIN teams tw ON tw.id = s.winner_team_id


        -- Tous les matchs de la confrontation (pour le comptage global)
        LEFT JOIN matches m_all
            ON m_all.series_id = s.id

        -- Uniquement les matchs terminés (pour progression & BO)
        LEFT JOIN matches m_done
            ON m_done.series_id = s.id
            AND m_done.is_completed = 1

        -- Résultats des matchs terminés
        LEFT JOIN match_teams mt
            ON mt.match_id = m_done.id

        WHERE s.tournament_id = ?
        {phase_filter_sql}

        GROUP BY s.id
        ORDER BY s.created_at
        """,
        tuple(params)
    ).fetchall()

    tiebreaks = db.execute(
        """
        SELECT id, scheduled_at, is_completed
        FROM matches
        WHERE tournament_id = ?
          AND series_id IS NULL
        ORDER BY created_at
        """,
        (tournament_id,)
    ).fetchall()

    return render_template(
        "admin/matches/index.html",
        tournaments=tournaments,
        selected_tournament=tournament,
        selected_phase_id=phase_id,
        confrontations=confrontations,
        tiebreaks=tiebreaks,
        phases=phases
    )


@admin_bp.route("/confrontations/create", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_confrontation_create():
    db = get_db()

    tournament_id = request.args.get("tournament_id", type=int)
    prefill_phase_id = request.args.get("phase_id", type=int)  # ✅ préfill depuis le filtre
    if not tournament_id:
        flash(_("Tournoi manquant."), "error")
        return redirect(url_for("admin.admin_matches"))

    tournament = db.execute(
        "SELECT * FROM tournaments WHERE id = ?",
        (tournament_id,)
    ).fetchone()

    if not tournament:
        flash(_("Tournoi introuvable."), "error")
        return redirect(url_for("admin.admin_matches"))

    # 🔹 Récupération des phases du tournoi
    phases = get_tournament_phases(db, tournament_id)

    if not phases:
        flash(
            _("Impossible de créer une confrontation : aucune phase n'est définie pour ce tournoi."),
            "error"
        )
        return redirect(url_for("admin.admin_matches", tournament_id=tournament_id))

    # --- POST : création ---
    if request.method == "POST":
        phase_id = request.form.get("phase_id", type=int)
        stage = (request.form.get("stage") or "").strip()
        best_of = request.form.get("best_of", type=int)
        round_value = request.form.get("round", type=int)

        team1_id = request.form.get("team1_id", type=int)
        team2_id = request.form.get("team2_id", type=int)

        # ✅ sources (progression bracket)
        source_team1_series_id = request.form.get("source_team1_series_id", type=int)
        source_team2_series_id = request.form.get("source_team2_series_id", type=int)
        source_team1_type = (request.form.get("source_team1_type") or "").strip() or None
        source_team2_type = (request.form.get("source_team2_type") or "").strip() or None

        # 🔒 Validation phase
        if not phase_id:
            flash(_("Une phase doit être sélectionnée."), "error")
            return redirect(request.url)

        phase = db.execute(
            """
            SELECT id, type
            FROM tournament_phases
            WHERE id = ? AND tournament_id = ?
            """,
            (phase_id, tournament_id)
        ).fetchone()

        if not phase:
            flash(_("Phase invalide pour ce tournoi."), "error")
            return redirect(request.url)

        phase_type = phase["type"]
        is_bracket = phase_type in ("bracket_simple_elim", "bracket_double_elim")

        # 🔒 round n'a de sens que pour les brackets
        if not is_bracket:
            round_value = None

        # 🔹 Récupération des équipes inscrites (pour validation si nécessaire)
        teams = db.execute(
            """
            SELECT t.id
            FROM teams t
            JOIN tournament_teams tt ON tt.team_id = t.id
            WHERE tt.tournament_id = ?
            """,
            (tournament_id,)
        ).fetchall()
        team_ids = {t["id"] for t in teams}

        # ✅ Validation équipes :
        # - bracket : équipes optionnelles (draft autorisé)
        # - non-bracket : 2 équipes obligatoires + règles existantes
        if not is_bracket:
            if not team1_id or not team2_id:
                flash(_("Les deux équipes doivent être sélectionnées."), "error")
                return redirect(request.url)

            if team1_id == team2_id:
                flash(_("Les deux équipes doivent être différentes."), "error")
                return redirect(request.url)

            if team1_id not in team_ids or team2_id not in team_ids:
                flash(_("Les équipes doivent être inscrites au tournoi."), "error")
                return redirect(request.url)
        else:
            # bracket : si une équipe est renseignée, elle doit être inscrite
            if team1_id and team1_id not in team_ids:
                flash(_("Équipe A invalide (non inscrite au tournoi)."), "error")
                return redirect(request.url)
            if team2_id and team2_id not in team_ids:
                flash(_("Équipe B invalide (non inscrite au tournoi)."), "error")
                return redirect(request.url)
            if team1_id and team2_id and team1_id == team2_id:
                flash(_("Les deux équipes doivent être différentes."), "error")
                return redirect(request.url)

            # ✅ Validation sources : uniquement bracket
            if team1_id and source_team1_series_id:
                flash(_("Équipe A : choisissez une équipe OU une source, pas les deux."), "error")
                return redirect(request.url)
            if team2_id and source_team2_series_id:
                flash(_("Équipe B : choisissez une équipe OU une source, pas les deux."), "error")
                return redirect(request.url)

            if source_team1_series_id and source_team1_type not in ("winner", "loser"):
                flash(_("Équipe A : le type de source doit être winner ou loser."), "error")
                return redirect(request.url)
            if source_team2_series_id and source_team2_type not in ("winner", "loser"):
                flash(_("Équipe B : le type de source doit être winner ou loser."), "error")
                return redirect(request.url)

            # sources doivent appartenir au même tournoi + même phase (cohérence bracket)
            if source_team1_series_id:
                ok = db.execute(
                    """
                    SELECT 1
                    FROM series
                    WHERE id = ? AND tournament_id = ? AND phase_id = ?
                    """,
                    (source_team1_series_id, tournament_id, phase_id)
                ).fetchone()
                if not ok:
                    flash(_("Source A invalide (doit être dans la même phase et le même tournoi)."), "error")
                    return redirect(request.url)

            if source_team2_series_id:
                ok = db.execute(
                    """
                    SELECT 1
                    FROM series
                    WHERE id = ? AND tournament_id = ? AND phase_id = ?
                    """,
                    (source_team2_series_id, tournament_id, phase_id)
                ).fetchone()
                if not ok:
                    flash(_("Source B invalide (doit être dans la même phase et le même tournoi)."), "error")
                    return redirect(request.url)

        db.execute(
            """
            INSERT INTO series (
                tournament_id,
                phase_id,
                team1_id,
                team2_id,
                stage,
                best_of,
                round,
                source_team1_series_id,
                source_team2_series_id,
                source_team1_type,
                source_team2_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tournament_id,
                phase_id,
                team1_id,
                team2_id,
                stage,
                best_of,
                round_value,
                source_team1_series_id,
                source_team2_series_id,
                source_team1_type,
                source_team2_type
            )
        )
        db.commit()

        flash(_("Confrontation créée."), "success")
        return redirect(url_for("admin.admin_matches", tournament_id=tournament_id, phase_id=phase_id))

    # --- GET : affichage du formulaire ---
    teams = db.execute(
        """
        SELECT t.id, t.name
        FROM teams t
        JOIN tournament_teams tt ON tt.team_id = t.id
        WHERE tt.tournament_id = ?
        ORDER BY t.name
        """,
        (tournament_id,)
    ).fetchall()

    # ✅ candidats sources : seulement si une phase est pré-sélectionnée
    source_candidates = []
    if prefill_phase_id:
        source_candidates = db.execute(
            """
            SELECT id, round, stage
            FROM series
            WHERE tournament_id = ?
              AND phase_id = ?
            ORDER BY COALESCE(round, 9999), id
            """,
            (tournament_id, prefill_phase_id)
        ).fetchall()

    return render_template(
        "admin/matches/confrontation_form.html",
        tournament=tournament,
        teams=teams,
        phases=phases,
        selected_phase_id=prefill_phase_id,  # ✅ pour préselection
        series=None,
        teams_locked=False,
        source_candidates=source_candidates  # ✅ pour les selects de source (template)
    )


@admin_bp.route("/matches/confrontations/<int:series_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_confrontation_edit(series_id):
    db = get_db()

    series = db.execute(
        "SELECT * FROM series WHERE id = ?",
        (series_id,)
    ).fetchone()

    if not series:
        flash(_("Confrontation introuvable."), "error")
        return redirect(url_for("admin.admin_matches"))

    tournament = db.execute(
        "SELECT * FROM tournaments WHERE id = ?",
        (series["tournament_id"],)
    ).fetchone()

    if tournament["status"] == "finished":
        flash(_("Tournoi terminé : modification impossible."), "error")
        return redirect(url_for("admin.admin_matches", tournament_id=tournament["id"]))

    phases = get_tournament_phases(db, tournament["id"])

    match_count = db.execute(
        "SELECT COUNT(*) FROM matches WHERE series_id = ?",
        (series_id,)
    ).fetchone()[0]

    teams = db.execute(
        """
        SELECT t.id, t.name
        FROM teams t
        JOIN tournament_teams tt ON tt.team_id = t.id
        WHERE tt.tournament_id = ?
        ORDER BY t.name
        """,
        (tournament["id"],)
    ).fetchall()

    team_ids = {t["id"] for t in teams}

    if request.method == "POST":
        phase_id = request.form.get("phase_id", type=int) or series["phase_id"]
        stage = (request.form.get("stage") or "").strip()
        best_of = request.form.get("best_of", type=int) or series["best_of"]
        round_value = request.form.get("round", type=int)

        # ✅ sources (progression bracket)
        source_team1_series_id = request.form.get("source_team1_series_id", type=int)
        source_team2_series_id = request.form.get("source_team2_series_id", type=int)
        source_team1_type = (request.form.get("source_team1_type") or "").strip() or None
        source_team2_type = (request.form.get("source_team2_type") or "").strip() or None

        if not phase_id:
            flash(_("Une phase doit être sélectionnée."), "error")
            return redirect(request.url)

        phase = db.execute(
            """
            SELECT id, type
            FROM tournament_phases
            WHERE id = ? AND tournament_id = ?
            """,
            (phase_id, tournament["id"])
        ).fetchone()

        if not phase:
            flash(_("Phase invalide pour ce tournoi."), "error")
            return redirect(request.url)

        phase_type = phase["type"]
        is_bracket = phase_type in ("bracket_simple_elim", "bracket_double_elim")

        # 🔒 round n'a de sens que pour les brackets
        if not is_bracket:
            round_value = None

        # équipes / phase / round / sources modifiables uniquement si aucun match
        if match_count == 0:
            team1_id = request.form.get("team1_id", type=int)
            team2_id = request.form.get("team2_id", type=int)

            if not is_bracket:
                # non-bracket : 2 équipes obligatoires
                if not team1_id or not team2_id:
                    flash(_("Les deux équipes doivent être sélectionnées."), "error")
                    return redirect(request.url)

                if team1_id == team2_id:
                    flash(_("Les deux équipes doivent être différentes."), "error")
                    return redirect(request.url)

                if team1_id not in team_ids or team2_id not in team_ids:
                    flash(_("Les équipes doivent être inscrites au tournoi."), "error")
                    return redirect(request.url)

                # non-bracket : on ignore les sources, par sécurité
                source_team1_series_id = None
                source_team2_series_id = None
                source_team1_type = None
                source_team2_type = None

            else:
                # bracket : équipes optionnelles
                if team1_id and team1_id not in team_ids:
                    flash(_("Équipe A invalide (non inscrite au tournoi)."), "error")
                    return redirect(request.url)
                if team2_id and team2_id not in team_ids:
                    flash(_("Équipe B invalide (non inscrite au tournoi)."), "error")
                    return redirect(request.url)
                if team1_id and team2_id and team1_id == team2_id:
                    flash(_("Les deux équipes doivent être différentes."), "error")
                    return redirect(request.url)

                # ✅ Validation sources
                if team1_id and source_team1_series_id:
                    flash(_("Équipe A : choisissez une équipe OU une source, pas les deux."), "error")
                    return redirect(request.url)
                if team2_id and source_team2_series_id:
                    flash(_("Équipe B : choisissez une équipe OU une source, pas les deux."), "error")
                    return redirect(request.url)

                if source_team1_series_id and source_team1_type not in ("winner", "loser"):
                    flash(_("Équipe A : le type de source doit être winner ou loser."), "error")
                    return redirect(request.url)
                if source_team2_series_id and source_team2_type not in ("winner", "loser"):
                    flash(_("Équipe B : le type de source doit être winner ou loser."), "error")
                    return redirect(request.url)

                # pas d'auto-référence
                if source_team1_series_id == series_id or source_team2_series_id == series_id:
                    flash(_("Une confrontation ne peut pas dépendre d'elle-même."), "error")
                    return redirect(request.url)

                # sources doivent appartenir au même tournoi + même phase
                if source_team1_series_id:
                    ok = db.execute(
                        """
                        SELECT 1
                        FROM series
                        WHERE id = ? AND tournament_id = ? AND phase_id = ?
                        """,
                        (source_team1_series_id, tournament["id"], phase_id)
                    ).fetchone()
                    if not ok:
                        flash(_("Source A invalide (doit être dans la même phase et le même tournoi)."), "error")
                        return redirect(request.url)

                if source_team2_series_id:
                    ok = db.execute(
                        """
                        SELECT 1
                        FROM series
                        WHERE id = ? AND tournament_id = ? AND phase_id = ?
                        """,
                        (source_team2_series_id, tournament["id"], phase_id)
                    ).fetchone()
                    if not ok:
                        flash(_("Source B invalide (doit être dans la même phase et le même tournoi)."), "error")
                        return redirect(request.url)

            db.execute(
                """
                UPDATE series
                SET
                    phase_id = ?,
                    team1_id = ?,
                    team2_id = ?,
                    stage = ?,
                    best_of = ?,
                    round = ?,
                    source_team1_series_id = ?,
                    source_team2_series_id = ?,
                    source_team1_type = ?,
                    source_team2_type = ?
                WHERE id = ?
                """,
                (
                    phase_id,
                    team1_id,
                    team2_id,
                    stage,
                    best_of,
                    round_value,
                    source_team1_series_id,
                    source_team2_series_id,
                    source_team1_type,
                    source_team2_type,
                    series_id
                )
            )
        else:
            # 🔒 conservateur v1 : on ne change pas phase/round/teams/sources si matchs existent
            db.execute(
                """
                UPDATE series
                SET stage = ?, best_of = ?
                WHERE id = ?
                """,
                (stage, best_of, series_id)
            )

        db.commit()
        flash(_("Confrontation mise à jour."), "success")
        return redirect(url_for("admin.admin_matches", tournament_id=tournament["id"], phase_id=phase_id))

    # ✅ candidats sources pour le template (même phase que la série)
    source_candidates = db.execute(
        """
        SELECT id, round, stage
        FROM series
        WHERE tournament_id = ?
          AND phase_id = ?
          AND id != ?
        ORDER BY COALESCE(round, 9999), id
        """,
        (tournament["id"], series["phase_id"], series_id)
    ).fetchall()

    return render_template(
        "admin/matches/confrontation_form.html",
        series=series,
        teams=teams,
        tournament=tournament,
        phases=phases,
        selected_phase_id=series["phase_id"],
        teams_locked=(match_count > 0),
        source_candidates=source_candidates
    )


@admin_bp.route("/matches/create", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_match_create():
    db = get_db()

    series_id = request.args.get("series_id", type=int) \
        or request.form.get("series_id", type=int)

    tournament_id = request.args.get("tournament_id", type=int) \
        or request.form.get("tournament_id", type=int)

    series = None
    tournament = None

    # --- Contexte ---
    if series_id:
        series = db.execute(
            """
            SELECT
                s.*,
                t1.name AS team1_name,
                t2.name AS team2_name
            FROM series s
            LEFT JOIN teams t1 ON t1.id = s.team1_id
            LEFT JOIN teams t2 ON t2.id = s.team2_id
            WHERE s.id = ?
            """,
            (series_id,)
        ).fetchone()

        if not series:
            flash(_("Confrontation introuvable."), "error")
            return redirect(url_for("admin.admin_matches"))

        tournament = db.execute(
            "SELECT * FROM tournaments WHERE id = ?",
            (series["tournament_id"],)
        ).fetchone()
        tournament_id = tournament["id"]

    else:
        tournament = db.execute(
            "SELECT * FROM tournaments WHERE id = ?",
            (tournament_id,)
        ).fetchone()

        if not tournament:
            flash(_("Tournoi introuvable."), "error")
            return redirect(url_for("admin.admin_matches"))

    if tournament["status"] == "finished":
        flash(_("Tournoi terminé : création impossible."), "error")
        return redirect(url_for("admin.admin_matches", tournament_id=tournament_id))

    # Équipes disponibles (pour tie-break)
    teams = db.execute(
        """
        SELECT t.id, t.name
        FROM teams t
        JOIN tournament_teams tt ON tt.team_id = t.id
        WHERE tt.tournament_id = ?
        ORDER BY t.name
        """,
        (tournament_id,)
    ).fetchall()
    team_ids = {t["id"] for t in teams}

    # --- POST ---
    if request.method == "POST":
        scheduled_at = request.form.get("scheduled_at")

        racetime_room_raw = request.form.get("racetime_room", "").strip()
        racetime_room = racetime_room_raw or None

        # Création du match
        cur = db.execute(
            """
            INSERT INTO matches (tournament_id, series_id, scheduled_at, racetime_room)
            VALUES (?, ?, ?, ?)
            """,
            (tournament_id, series_id, scheduled_at, racetime_room)
        )
        match_id = cur.lastrowid
        # Création des lignes match_teams pour une confrontation
        if series_id:
            db.execute(
                """
                INSERT INTO match_teams (match_id, team_id)
                VALUES (?, ?)
                """,
                (match_id, series["team1_id"])
            )
            db.execute(
                """
                INSERT INTO match_teams (match_id, team_id)
                VALUES (?, ?)
                """,
                (match_id, series["team2_id"])
            )

        # Tie-break multi-équipes
        if not series_id:
            selected_teams = request.form.getlist("team_ids")
            selected_teams = [int(t) for t in selected_teams if t.isdigit()]

            if len(selected_teams) < 2:
                flash(_("Un tie-break doit contenir au moins 2 équipes."), "error")
                db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
                db.commit()
                return redirect(request.url)

            if not all(tid in team_ids for tid in selected_teams):
                flash(_("Toutes les équipes doivent être inscrites au tournoi."), "error")
                db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
                db.commit()
                return redirect(request.url)

            for tid in selected_teams:
                db.execute(
                    """
                    INSERT INTO match_teams (match_id, team_id)
                    VALUES (?, ?)
                    """,
                    (match_id, tid)
                )

        db.commit()
        flash(_("Match créé."), "success")

        if series_id:
            return redirect(
                url_for("admin.admin_confrontation_matches", series_id=series_id)
            )

        return redirect(
            url_for("admin.admin_matches", tournament_id=tournament_id)
        )

    return render_template(
        "admin/matches/match_form.html",
        series=series,
        tournament=tournament,
        teams=teams
    )


@admin_bp.route("/matches/confrontations/<int:series_id>/matches")
@login_required
@role_required("admin")
def admin_confrontation_matches(series_id):
    db = get_db()

    series = db.execute(
        """
        SELECT
            s.*,
            p.name AS phase_name,
            p.position AS phase_position,
            t1.name AS team1_name,
            t2.name AS team2_name,
            tw.name AS winner_name,

            SUM(
                CASE
                    WHEN mt.team_id = s.team1_id AND mt.is_winner = 1 THEN 1
                    ELSE 0
                END
            ) AS team1_wins,

            SUM(
                CASE
                    WHEN mt.team_id = s.team2_id AND mt.is_winner = 1 THEN 1
                    ELSE 0
                END
            ) AS team2_wins

        FROM series s
        JOIN tournament_phases p ON p.id = s.phase_id
        LEFT JOIN teams t1 ON t1.id = s.team1_id
        LEFT JOIN teams t2 ON t2.id = s.team2_id
        LEFT JOIN teams tw ON tw.id = s.winner_team_id

        LEFT JOIN matches m
            ON m.series_id = s.id
            AND m.is_completed = 1

        LEFT JOIN match_teams mt
            ON mt.match_id = m.id

        WHERE s.id = ?
        GROUP BY s.id
        """,
        (series_id,)
    ).fetchone()


    if not series:
        flash(_("Confrontation introuvable."), "error")
        return redirect(url_for("admin.admin_matches"))

    matches = db.execute(
        """
        SELECT *
        FROM matches
        WHERE series_id = ?
        ORDER BY match_index, created_at
        """,
        (series_id,)
    ).fetchall()

    return render_template(
        "admin/matches/confrontation_matches.html",
        series=series,
        matches=matches
    )
    
    
@admin_bp.route(
    "/matches/<int:match_id>/edit",
    methods=["GET", "POST"]
)
@login_required
@role_required("admin")
def admin_match_edit(match_id):
    db = get_db()

    match = db.execute(
        "SELECT * FROM matches WHERE id = ?",
        (match_id,)
    ).fetchone()

    if not match:
        flash(_("Match introuvable."), "error")
        return redirect(url_for("admin.admin_matches"))

    tournament = db.execute(
        "SELECT * FROM tournaments WHERE id = ?",
        (match["tournament_id"],)
    ).fetchone()

    if tournament["status"] == "finished":
        flash(_("Tournoi terminé : modification impossible."), "error")
        return redirect(
            url_for("admin.admin_matches", tournament_id=tournament["id"])
        )
        
    series = None
    if match["series_id"]:
        series = db.execute(
            """
            SELECT s.*,
                   t1.name AS team1_name,
                   t2.name AS team2_name
            FROM series s
            LEFT JOIN teams t1 ON t1.id = s.team1_id
            LEFT JOIN teams t2 ON t2.id = s.team2_id
            WHERE s.id = ?
            """,
            (match["series_id"],)
        ).fetchone()

    if request.method == "POST":
        scheduled_at = request.form.get("scheduled_at")

        racetime_room_raw = request.form.get("racetime_room", "").strip()
        racetime_room = racetime_room_raw or None

        db.execute(
            """
            UPDATE matches
            SET scheduled_at = ?, racetime_room = ?
            WHERE id = ?
            """,
            (scheduled_at, racetime_room, match_id)
        )
        db.commit()

        flash(_("Match mis à jour."), "success")
        return redirect(
            url_for("admin.admin_matches", tournament_id=tournament["id"])
        )

    return render_template(
        "admin/matches/match_form.html",
        match=match,
        tournament=tournament,
        series=series,
        series_id=match["series_id"]
    )

@admin_bp.route(
    "/matches/confrontations/<int:series_id>/delete",
    methods=["POST"]
)
@login_required
@role_required("admin")
def admin_confrontation_delete(series_id):
    db = get_db()

    match_count = db.execute(
        "SELECT COUNT(*) FROM matches WHERE series_id = ?",
        (series_id,)
    ).fetchone()[0]

    if match_count > 0:
        flash(_("Impossible de supprimer une confrontation avec des matchs."), "error")
        return redirect(url_for("admin.admin_matches"))

    db.execute("DELETE FROM series WHERE id = ?", (series_id,))
    db.commit()

    flash(_("Confrontation supprimée."), "success")
    return redirect(url_for("admin.admin_matches"))

@admin_bp.route(
    "/matches/<int:match_id>/delete",
    methods=["POST"]
)
@login_required
@role_required("admin")
def admin_match_delete(match_id):
    db = get_db()

    match = db.execute(
        "SELECT * FROM matches WHERE id = ?",
        (match_id,)
    ).fetchone()

    if not match:
        flash(_("Match introuvable."), "error")
        return redirect(url_for("admin.admin_matches"))

    series_id = match["series_id"]
    was_completed = match["is_completed"]

    db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    db.commit()

    # 🔁 Recalcul du vainqueur si nécessaire
    if series_id and was_completed:
        from app.modules.results import update_series_result
        update_series_result(series_id)

    flash(_("Match supprimé."), "success")

    if series_id:
        return redirect(
            url_for("admin.admin_confrontation_matches", series_id=series_id)
        )

    return redirect(
        url_for("admin.admin_matches", tournament_id=match["tournament_id"])
    )



@admin_bp.route(
    "/matches/<int:match_id>/results",
    methods=["GET", "POST"]
)
@login_required
@role_required("admin")
def admin_match_results(match_id):
    db = get_db()

    # --- Match ---
    match = db.execute(
        """
        SELECT *
        FROM matches
        WHERE id = ?
        """,
        (match_id,)
    ).fetchone()

    if not match:
        flash(_("Match introuvable."), "error")
        return redirect(url_for("admin.admin_matches"))

    # --- Équipes du match ---
    teams = db.execute(
        """
        SELECT
            mt.team_id,
            t.name,
            mt.final_time_raw,
            mt.final_time,
            mt.position,
            mt.is_winner
        FROM match_teams mt
        JOIN teams t ON t.id = mt.team_id
        WHERE mt.match_id = ?
        ORDER BY mt.position ASC, t.name
        """,
        (match_id,)
    ).fetchall()

    if request.method == "POST":
        results = []
        errors = False

        from app.modules.results import parse_final_time, InvalidResultFormat

        # --- Parsing ---
        for t in teams:
            field_name = f"result_{t['team_id']}"
            raw_value = request.form.get(field_name, "").strip()

            try:
                final_time, status = parse_final_time(raw_value)
            except InvalidResultFormat as e:
                flash(f"{t['name']} : {str(e)}", "error")
                errors = True
                continue

            results.append({
                "team_id": t["team_id"],
                "final_time_raw": raw_value.upper(),
                "final_time": final_time,
                "status": status
            })

        if errors:
            return redirect(request.url)

        # --- Classement ---
        timed = [r for r in results if r["final_time"] is not None]
        others = [r for r in results if r["final_time"] is None]

        timed.sort(key=lambda r: r["final_time"])

        ordered = timed + others

        # Détection d'égalité pour la première place
        first_time = ordered[0]["final_time"]

        is_tie_for_first = (
            first_time is not None and
            sum(1 for r in ordered if r["final_time"] == first_time) > 1
        )
        
        # --- Mise à jour ---
        for idx, r in enumerate(ordered, start=1):
            is_winner = 1 if idx == 1 and not is_tie_for_first else 0


            db.execute(
                """
                UPDATE match_teams
                SET
                    final_time_raw = ?,
                    final_time = ?,
                    position = ?,
                    is_winner = ?
                WHERE match_id = ?
                  AND team_id = ?
                """,
                (
                    r["final_time_raw"],
                    r["final_time"],
                    idx,
                    is_winner,
                    match_id,
                    r["team_id"]
                )
            )

        db.execute(
            "UPDATE matches SET is_completed = 1 WHERE id = ?",
            (match_id,)
        )

        db.commit()
        
        if match["series_id"]:
            from app.modules.results import update_series_result
            update_series_result(match["series_id"])


        flash(_("Résultats enregistrés."), "success")
        if match["series_id"]:
            return redirect(
                url_for(
                    "admin.admin_confrontation_matches",
                    series_id=match["series_id"]
                )
            )
        else:
            return redirect(
                url_for(
                    "admin.admin_matches",
                    tournament_id=match["tournament_id"]
                )
            )

    return render_template(
        "admin/matches/match_results.html",
        match=match,
        teams=teams
    )

@admin_bp.route(
    "/matches/<int:match_id>/results/racetime/prefill",
    methods=["GET"]
)
@login_required
@role_required("admin")
def admin_match_results_racetime_prefill(match_id: int):
    try:
        db = get_db()

        # 1) Match + racetime_room
        match = db.execute(
            "SELECT id, racetime_room FROM matches WHERE id = ?",
            (match_id,)
        ).fetchone()

        if not match:
            return jsonify({"ok": False, "error": "Match introuvable."}), 404

        racetime_room = (match["racetime_room"] or "").strip()
        if not racetime_room:
            return jsonify({"ok": False, "error": "Aucune room racetime associée à ce match."}), 400

        # 2) Teams du match
        teams = db.execute(
            """
            SELECT mt.team_id
            FROM match_teams mt
            WHERE mt.match_id = ?
            """,
            (match_id,)
        ).fetchall()

        if not teams:
            return jsonify({"ok": False, "error": "Aucune équipe associée à ce match."}), 400

        team_ids = [t["team_id"] for t in teams]

        # 3) Récupérer TOUS les racetime_user de chaque team (co-op support)
        #    (team time = last finisher time, géré dans le module racetime)
        placeholders = ",".join(["?"] * len(team_ids))
        rows = db.execute(
            f"""
            SELECT
                tp.team_id,
                p.racetime_user
            FROM team_players tp
            JOIN players p ON p.id = tp.player_id
            WHERE tp.team_id IN ({placeholders})
            ORDER BY tp.team_id, tp.position ASC
            """,
            tuple(team_ids)
        ).fetchall()

        team_to_users: dict[int, list[str]] = {tid: [] for tid in team_ids}
        for r in rows:
            tid = r["team_id"]
            rt = (r["racetime_user"] or "").strip()
            if rt:
                team_to_users[tid].append(rt)

        # Si une team n'a aucun racetime_user, on refuse (plus clair pour le MVP)
        missing_team_ids = [tid for tid, users in team_to_users.items() if not users]
        if missing_team_ids:
            return jsonify({
                "ok": False,
                "error": "Certaines équipes n'ont pas de racetime_user renseigné (players).",
                "missing_team_ids": missing_team_ids
            }), 400

        # 4) Fetch racetime + build results payload
        try:
            race_json = racetime_mod.fetch_race_data(racetime_room)
            results, meta = racetime_mod.build_prefill_payload_for_teams(team_to_users, race_json)
        except racetime_mod.RacetimeRoomInvalid:
            return jsonify({"ok": False, "error": "URL racetime invalide."}), 400
        except racetime_mod.RacetimeFetchError:
            return jsonify({"ok": False, "error": "Impossible de contacter racetime ou réponse invalide."}), 502

        # Si on ne peut rien calculer pour certaines teams, on renvoie quand même (préfill partiel possible)
        return jsonify({
            "ok": True,
            "results": results,
            "meta": meta
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@admin_bp.route(
    "/tournaments/<int:tournament_id>/phases/create",
    methods=["POST"]
)
@login_required
@role_required("admin")
def admin_tournament_phase_create(tournament_id):
    db = get_db()

    tournament = db.execute(
        "SELECT id FROM tournaments WHERE id = ?",
        (tournament_id,)
    ).fetchone()

    if not tournament:
        flash(_("Tournoi introuvable."), "error")
        return redirect(url_for("admin.tournaments_list"))

    name = request.form.get("name", "").strip()
    phase_type = request.form.get("type", "custom")
    position = request.form.get("position", type=int)

    if not name:
        flash(_("Le nom de la phase est obligatoire."), "error")
        return redirect(
            url_for("admin.admin_tournament_edit", tournament_id=tournament_id)
        )

    if position is None or position < 1:
        flash(_("La position de la phase est invalide."), "error")
        return redirect(
            url_for("admin.admin_tournament_edit", tournament_id=tournament_id)
        )
        
        
    qualifiers = request.form.get("qualifiers_per_group", "").strip()

    details_obj = {}
    details_json = None

    if phase_type == "groups":
        if qualifiers:
            try:
                q = int(qualifiers)
                if q < 1:
                    raise ValueError()
                details_obj["qualifiers_per_group"] = q
            except ValueError:
                flash(_("Le nombre de qualifiés par groupe est invalide."), "error")
                return redirect(url_for("admin.admin_tournament_edit", tournament_id=tournament_id))

        details_json = json.dumps(details_obj, ensure_ascii=False) if details_obj else None
    else:
        details_json = None


    db.execute(
        """
        INSERT INTO tournament_phases (tournament_id, name, type, position, details)
        VALUES (?, ?, ?, ?, ?)
        """,
        (tournament_id, name, phase_type, position, details_json)
    )
    db.commit()

    flash(_("Phase créée."), "success")
    return redirect(
        url_for("admin.admin_tournament_edit", tournament_id=tournament_id)
    )

@admin_bp.route(
    "/tournaments/<int:tournament_id>/phases/<int:phase_id>/edit",
    methods=["POST"]
)
@login_required
@role_required("admin")
def admin_tournament_phase_edit(tournament_id, phase_id):
    db = get_db()

    phase = db.execute(
        """
        SELECT id
        FROM tournament_phases
        WHERE id = ? AND tournament_id = ?
        """,
        (phase_id, tournament_id)
    ).fetchone()

    if not phase:
        flash(_("Phase introuvable pour ce tournoi."), "error")
        return redirect(
            url_for("admin.admin_tournament_edit", tournament_id=tournament_id)
        )

    name = request.form.get("name", "").strip()
    phase_type = request.form.get("type", "custom")
    position = request.form.get("position", type=int)

    if not name:
        flash(_("Le nom de la phase est obligatoire."), "error")
        return redirect(
            url_for("admin.admin_tournament_edit", tournament_id=tournament_id)
        )

    if position is None or position < 1:
        flash(_("La position de la phase est invalide."), "error")
        return redirect(
            url_for("admin.admin_tournament_edit", tournament_id=tournament_id)
        )
        
    qualifiers = request.form.get("qualifiers_per_group", "").strip()

    details_obj = {}
    details_json = None

    if phase_type == "groups":
        if qualifiers:
            try:
                q = int(qualifiers)
                if q < 1:
                    raise ValueError()
                details_obj["qualifiers_per_group"] = q
            except ValueError:
                flash(_("Le nombre de qualifiés par groupe est invalide."), "error")
                return redirect(url_for("admin.admin_tournament_edit", tournament_id=tournament_id))
    
        # Si on a au moins une clé, on stocke du JSON, sinon on laisse NULL
        details_json = json.dumps(details_obj, ensure_ascii=False) if details_obj else None
    else:
        details_json = None


    db.execute(
        """
        UPDATE tournament_phases
        SET name = ?, type = ?, position = ?, details = ?
        WHERE id = ?
        """,
        (name, phase_type, position, details_json, phase_id)
    )
    db.commit()

    flash(_("Phase mise à jour."), "success")
    return redirect(
        url_for("admin.admin_tournament_edit", tournament_id=tournament_id)
    )

@admin_bp.route(
    "/tournaments/<int:tournament_id>/phases/<int:phase_id>/delete",
    methods=["POST"]
)
@login_required
@role_required("admin")
def admin_tournament_phase_delete(tournament_id, phase_id):
    db = get_db()

    phase = db.execute(
        """
        SELECT id
        FROM tournament_phases
        WHERE id = ? AND tournament_id = ?
        """,
        (phase_id, tournament_id)
    ).fetchone()

    if not phase:
        flash(_("Phase introuvable pour ce tournoi."), "error")
        return redirect(
            url_for("admin.admin_tournament_edit", tournament_id=tournament_id)
        )

    used = db.execute(
        """
        SELECT 1
        FROM series
        WHERE phase_id = ?
        LIMIT 1
        """,
        (phase_id,)
    ).fetchone()

    if used:
        flash(
            _("Impossible de supprimer cette phase : des confrontations y sont rattachées."),
            "error"
        )
        return redirect(
            url_for("admin.admin_tournament_edit", tournament_id=tournament_id)
        )

    db.execute(
        "DELETE FROM tournament_phases WHERE id = ?",
        (phase_id,)
    )
    db.commit()

    flash(_("Phase supprimée."), "success")
    return redirect(
        url_for("admin.admin_tournament_edit", tournament_id=tournament_id)
    )

@admin_bp.route("/trackers")
@login_required
@role_required("admin")
def admin_trackers_index():
    """
    Admin – List available trackers with presets count.
    """
    trackers = get_available_trackers()

    trackers_list = []

    for tracker in trackers:
        tracker_type = tracker["key"]

        try:
            presets = list_presets(tracker_type)
            presets_count = len(presets)
        except Exception:
            presets_count = 0

        trackers_list.append({
            "tracker_type": tracker_type,
            "label": tracker["label"],
            "presets_count": presets_count,
        })

    trackers_list.sort(key=lambda x: x["label"].lower())

    return render_template(
        "admin/trackers/index.html",
        trackers=trackers_list,
    )

    
@admin_bp.route("/trackers/<tracker_type>/presets")
@login_required
@role_required("admin")
def admin_trackers_presets(tracker_type):
    """
    Admin – List presets for a given tracker.
    """
    tracker_def = get_tracker_definition(tracker_type)

    presets = list_presets(tracker_type)

    # Tri UX (label)
    presets.sort(key=lambda x: (x.get("label") or "").lower())

    return render_template(
        "admin/trackers/presets_list.html",
        tracker_type=tracker_type,
        tracker_label=tracker_def["label"],
        presets=presets,
    )
    
    
def _get_default_participant_for_tracker(tracker_type: str) -> dict:
    """
    Génère un participant (1 slot) via la factory default_preset du registry.
    Supporte {"participants": [...]} et fallback participant dict.
    """
    tracker_def = get_tracker_definition(tracker_type)
    preset_factory = tracker_def["default_preset"]

    data = preset_factory(participants_count=1)

    if isinstance(data, dict) and "participants" in data and data["participants"]:
        participant = data["participants"][0]
    elif isinstance(data, dict):
        participant = data
    else:
        raise ValueError(
            f"Invalid default preset structure for tracker_type={tracker_type}"
        )

    participant.setdefault("slot", 1)
    participant.setdefault("team_id", 1)
    participant.setdefault("label", "Preset")

    return participant
    
@admin_bp.route("/trackers/<tracker_type>/presets/new", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_trackers_preset_new(tracker_type):
    tracker_def = get_tracker_definition(tracker_type)

    if request.method == "POST":
        label = (request.form.get("label") or "").strip()
        notes = (request.form.get("notes") or "").strip()
        participant_json = request.form.get("participant_json") or "{}"

        if not label:
            flash(_("Le nom du preset est obligatoire."), "error")
        else:
            try:
                participant = json.loads(participant_json)
            except Exception:
                participant = {}

            preset_slug = create_preset(
                tracker_type=tracker_type,
                label=label,
                participant=participant,
                notes=notes,
            )
            flash(_("Preset créé."), "success")
            return redirect(url_for(
                "admin.admin_trackers_preset_edit",
                tracker_type=tracker_type,
                preset_slug=preset_slug
            ))

    participant = _get_default_participant_for_tracker(tracker_type)
    tracker_catalog = tracker_def["catalog"]()

    return render_template(
        "admin/trackers/preset_edit.html",
        mode="new",
        tracker_type=tracker_type,
        tracker_label=tracker_def["label"],
        preset_slug=None,
        label="",
        notes="",
        participant=participant,
        tracker_catalog=tracker_catalog,
        tracker_frontend=tracker_def["frontend"],
    )


@admin_bp.route("/trackers/<tracker_type>/presets/<preset_slug>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_trackers_preset_edit(tracker_type, preset_slug):
    tracker_def = get_tracker_definition(tracker_type)
    preset = load_preset(tracker_type, preset_slug)

    if request.method == "POST":
        new_label = (request.form.get("label") or "").strip()
        notes = (request.form.get("notes") or "").strip()
        participant_json = request.form.get("participant_json") or "{}"

        if not new_label:
            flash(_("Le nom du preset est obligatoire."), "error")
        else:
            try:
                participant = json.loads(participant_json)
            except Exception:
                participant = {}

            # Rename si label change
            current_label = preset.get("label", "")
            if new_label != current_label:
                preset_slug = rename_preset(tracker_type, preset_slug, new_label)

            # Save contenu
            data = preset
            data["label"] = new_label
            data["notes"] = notes
            data["participant"] = participant

            save_preset(tracker_type, preset_slug, data)

            flash(_("Preset enregistré."), "success")
            return redirect(url_for(
                "admin.admin_trackers_preset_edit",
                tracker_type=tracker_type,
                preset_slug=preset_slug
            ))
    tracker_catalog = tracker_def["catalog"]()

    return render_template(
        "admin/trackers/preset_edit.html",
        mode="edit",
        tracker_type=tracker_type,
        tracker_label=tracker_def["label"],
        preset_slug=preset_slug,
        label=preset.get("label", preset_slug),
        notes=preset.get("notes", ""),
        participant=preset.get("participant", {}),
        tracker_catalog=tracker_catalog,
        tracker_frontend=tracker_def["frontend"],
    )
    
@admin_bp.route(
    "/trackers/<tracker_type>/presets/<preset_slug>/delete",
    methods=["POST"],
)
@login_required
@role_required("admin")
def admin_trackers_preset_delete(tracker_type, preset_slug):
    """
    Admin – Delete a preset.
    """
    # Vérifie que le tracker existe (cohérence UX)
    get_tracker_definition(tracker_type)

    try:
        delete_preset(tracker_type, preset_slug)
        flash(_("Preset supprimé."), "success")
    except FileNotFoundError:
        flash(_("Preset introuvable."), "error")

    return redirect(
        url_for(
            "admin.admin_trackers_presets",
            tracker_type=tracker_type,
        )
    )
    
@admin_bp.route("/translations")
@login_required
@role_required("admin")
def translations_hub():
    db = get_db()

    # Langue cible (par défaut en)
    lang = (request.args.get("lang") or "en").strip().lower()

    # --- TOURNOIS ---
    tournaments_total = db.execute(
        "SELECT COUNT(*) AS n FROM tournaments"
    ).fetchone()["n"]

    tournaments_name_done = db.execute(
        """
        SELECT COUNT(*) AS n
        FROM tournaments t
        JOIN translations tr
          ON tr.entity_type='tournament'
         AND tr.entity_key=t.slug
         AND tr.field='name'
         AND tr.lang=?
        """,
        (lang,)
    ).fetchone()["n"]

    tournaments_metadata_done = db.execute(
        """
        SELECT COUNT(*) AS n
        FROM tournaments t
        JOIN translations tr
          ON tr.entity_type='tournament'
         AND tr.entity_key=t.slug
         AND tr.field='metadata'
         AND tr.lang=?
        """,
        (lang,)
    ).fetchone()["n"]

    # --- PHASES ---
    phases_total = db.execute(
        "SELECT COUNT(*) AS n FROM tournament_phases"
    ).fetchone()["n"]

    phases_done = db.execute(
        """
        SELECT COUNT(*) AS n
        FROM tournament_phases p
        JOIN translations tr
          ON tr.entity_type='tournament_phase'
         AND tr.entity_key=CAST(p.id AS TEXT)
         AND tr.field='name'
         AND tr.lang=?
        """,
        (lang,)
    ).fetchone()["n"]

    # --- GROUPES (distinct) ---
    groups_total = db.execute(
        """
        SELECT COUNT(*) AS n
        FROM (
          SELECT DISTINCT (t.slug || '|' || tt.group_name) AS k
          FROM tournament_teams tt
          JOIN tournaments t ON t.id = tt.tournament_id
          WHERE t.slug IS NOT NULL AND t.slug <> ''
            AND tt.group_name IS NOT NULL AND tt.group_name <> ''
        )
        """
    ).fetchone()["n"]

    groups_done = db.execute(
        """
        SELECT COUNT(*) AS n
        FROM (
          SELECT DISTINCT (t.slug || '|' || tt.group_name) AS k
          FROM tournament_teams tt
          JOIN tournaments t ON t.id = tt.tournament_id
          WHERE t.slug IS NOT NULL AND t.slug <> ''
            AND tt.group_name IS NOT NULL AND tt.group_name <> ''
        ) g
        JOIN translations tr
          ON tr.entity_type='tournament_group'
         AND tr.entity_key=g.k
         AND tr.field='name'
         AND tr.lang=?
        """,
        (lang,)
    ).fetchone()["n"]

    stats = {
        "lang": lang,
        "tournaments": {
            "total": tournaments_total,
            "name_done": tournaments_name_done,
            "metadata_done": tournaments_metadata_done,
        },
        "phases": {
            "total": phases_total,
            "done": phases_done,
        },
        "groups": {
            "total": groups_total,
            "done": groups_done,
        },
    }

    return render_template("admin/translations/hub.html", stats=stats)

@admin_bp.route("/translations/tournaments")
@login_required
@role_required("admin")
def translations_tournaments():
    db = get_db()
    lang = (request.args.get("lang") or "en").strip().lower()
    only_missing = (request.args.get("only_missing") == "1")

    tournaments = db.execute(
        "SELECT id, slug, name, metadata FROM tournaments ORDER BY id DESC"
    ).fetchall()

    rows = []
    for t in tournaments:
        slug = t["slug"]

        # Traductions existantes
        name_tr = get_translation("tournament", slug, "name", lang) if slug else None
        meta_tr = get_translation("tournament", slug, "metadata", lang) if slug else None

        name_done = bool(name_tr)
        metadata_done = bool(meta_tr)

        # Groupes (distinct) pour ce tournoi : total + traduits
        groups_total = db.execute(
            """
            SELECT COUNT(*) AS n
            FROM (
              SELECT DISTINCT group_name
              FROM tournament_teams
              WHERE tournament_id = ?
                AND group_name IS NOT NULL
                AND group_name <> ''
            )
            """,
            (t["id"],)
        ).fetchone()["n"]

        if groups_total > 0 and slug:
            groups_done = db.execute(
                """
                SELECT COUNT(*) AS n
                FROM (
                  SELECT DISTINCT (? || '|' || group_name) AS k
                  FROM tournament_teams
                  WHERE tournament_id = ?
                    AND group_name IS NOT NULL
                    AND group_name <> ''
                ) g
                JOIN translations tr
                  ON tr.entity_type='tournament_group'
                 AND tr.entity_key=g.k
                 AND tr.field='name'
                 AND tr.lang=?
                """,
                (slug, t["id"], lang)
            ).fetchone()["n"]
        else:
            groups_done = 0

        # Filtre "manquants seulement"
        # Ici : on considère "traduit" si NAME + METADATA sont traduits (groupes séparés)
        if only_missing and name_done and metadata_done:
            continue

        rows.append({
            "id": t["id"],
            "slug": slug,
            "name_db": t["name"],
            "name_done": name_done,
            "metadata_done": metadata_done,
            "groups_total": groups_total,
            "groups_done": groups_done,
        })

    return render_template(
        "admin/translations/tournaments_list.html",
        lang=lang,
        only_missing=only_missing,
        rows=rows
    )


@admin_bp.route("/translations/tournaments/<slug>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def translations_tournament_detail(slug):
    db = get_db()
    lang = (request.args.get("lang") or "en").strip().lower()

    tournament = db.execute(
        "SELECT id, slug, name, metadata FROM tournaments WHERE slug = ?",
        (slug,)
    ).fetchone()

    if not tournament:
        abort(404)

    # Stats groupes pour ce tournoi (distinct group_name)
    groups_total = db.execute(
        """
        SELECT COUNT(*) AS n
        FROM (
          SELECT DISTINCT group_name
          FROM tournament_teams
          WHERE tournament_id = ?
            AND group_name IS NOT NULL
            AND group_name <> ''
        )
        """,
        (tournament["id"],)
    ).fetchone()["n"]

    if groups_total > 0:
        groups_done = db.execute(
            """
            SELECT COUNT(*) AS n
            FROM (
              SELECT DISTINCT (? || '|' || group_name) AS k
              FROM tournament_teams
              WHERE tournament_id = ?
                AND group_name IS NOT NULL
                AND group_name <> ''
            ) g
            JOIN translations tr
              ON tr.entity_type='tournament_group'
             AND tr.entity_key=g.k
             AND tr.field='name'
             AND tr.lang=?
            """,
            (slug, tournament["id"], lang)
        ).fetchone()["n"]
    else:
        groups_done = 0

    if request.method == "POST":
        name_tr = request.form.get("name_tr", "")
        metadata_tr = request.form.get("metadata_tr", "")

        name_tr_clean = name_tr.strip()
        metadata_tr_clean = metadata_tr.strip()

        # Validation JSON si metadata non vide
        if metadata_tr_clean:
            try:
                json.loads(metadata_tr_clean)
            except Exception:
                flash(_("Metadata invalide : JSON incorrect."), "error")
                return render_template(
                    "admin/translations/tournament_detail.html",
                    lang=lang,
                    tournament={
                        "id": tournament["id"],
                        "slug": tournament["slug"],
                        "name_db": tournament["name"],
                        "metadata_db": tournament["metadata"],
                    },
                    translation={
                        "name": name_tr,
                        "metadata": metadata_tr,
                    },
                    groups_total=groups_total,
                    groups_done=groups_done,
                )

        from app.modules.i18n import upsert_translation

        upsert_translation("tournament", slug, "name", lang, name_tr_clean if name_tr_clean else None)
        upsert_translation("tournament", slug, "metadata", lang, metadata_tr_clean if metadata_tr_clean else None)

        flash(_("Traductions enregistrées."), "success")
        return redirect(url_for("admin.translations_tournament_detail", slug=slug, lang=lang))

    # GET
    name_tr = get_translation("tournament", slug, "name", lang) or ""
    metadata_tr = get_translation("tournament", slug, "metadata", lang) or ""

    return render_template(
        "admin/translations/tournament_detail.html",
        lang=lang,
        tournament={
            "id": tournament["id"],
            "slug": tournament["slug"],
            "name_db": tournament["name"],
            "metadata_db": tournament["metadata"],
        },
        translation={
            "name": name_tr,
            "metadata": metadata_tr,
        },
        groups_total=groups_total,
        groups_done=groups_done,
    )



@admin_bp.route("/translations/phases", methods=["GET"])
@login_required
@role_required("admin")
def translations_phases():
    db = get_db()
    lang = (request.args.get("lang") or "en").strip().lower()
    only_missing = (request.args.get("only_missing") == "1")

    phases = db.execute(
        "SELECT id, name FROM tournament_phases ORDER BY id ASC"
    ).fetchall()

    rows = []
    for p in phases:
        phase_id = p["id"]
        phase_key = str(phase_id)

        tr = get_translation("tournament_phase", phase_key, "name", lang)
        done = bool(tr)

        if only_missing and done:
            continue

        rows.append({
            "id": phase_id,
            "name_db": p["name"],
            "name_tr": tr or "",
            "done": done,
        })

    return render_template(
        "admin/translations/phases_list.html",
        lang=lang,
        only_missing=only_missing,
        rows=rows
    )


@admin_bp.route("/translations/phases", methods=["POST"])
@login_required
@role_required("admin")
def translations_phases_save():
    db = get_db()
    lang = (request.args.get("lang") or "en").strip().lower()
    only_missing = (request.args.get("only_missing") == "1")

    # On relit toutes les phases pour savoir quelles clés attendre
    phases = db.execute(
        "SELECT id FROM tournament_phases"
    ).fetchall()

    from app.modules.i18n import upsert_translation

    # Bulk save : chaque input s'appelle phase_<id>
    for p in phases:
        phase_id = p["id"]
        key = str(phase_id)
        field_name = f"phase_{phase_id}"

        # Si l’input n’est pas dans le form, on ignore (robuste)
        if field_name not in request.form:
            continue

        value = request.form.get(field_name, "")
        value_clean = value.strip()

        # upsert_translation: doit delete si vide (comme tu l’as mis)
        upsert_translation("tournament_phase", key, "name", lang, value_clean if value_clean else None)

    flash(_("Traductions des phases enregistrées."), "success")
    return redirect(url_for("admin.translations_phases", lang=lang, only_missing=("1" if only_missing else None)))

@admin_bp.route("/translations/tournaments/<slug>/groups", methods=["GET", "POST"])
@login_required
@role_required("admin")
def translations_tournament_groups(slug):
    db = get_db()
    lang = (request.args.get("lang") or "en").strip().lower()
    only_missing = (request.args.get("only_missing") == "1")

    # Vérifier que le tournoi existe
    tournament = db.execute(
        "SELECT id, slug, name FROM tournaments WHERE slug = ?",
        (slug,)
    ).fetchone()

    if not tournament:
        abort(404)

    # Récupérer les group_name distincts pour ce tournoi
    groups = db.execute(
        """
        SELECT DISTINCT group_name
        FROM tournament_teams
        WHERE tournament_id = ?
          AND group_name IS NOT NULL
          AND group_name <> ''
        ORDER BY group_name ASC
        """,
        (tournament["id"],)
    ).fetchall()

    from app.modules.i18n import get_translation, upsert_translation

    rows = []

    if request.method == "POST":
        # Bulk save
        for g in groups:
            group_name = g["group_name"]
            field_name = f"group_{group_name}"

            if field_name not in request.form:
                continue

            value = request.form.get(field_name, "")
            value_clean = value.strip()

            key = f"{slug}|{group_name}"

            # value vide => suppression (fallback DB)
            upsert_translation(
                "tournament_group",
                key,
                "name",
                lang,
                value_clean if value_clean else None
            )

        flash(_("Traductions des groupes enregistrées."), "success")
        return redirect(
            url_for(
                "admin.translations_tournament_groups",
                slug=slug,
                lang=lang,
                only_missing=("1" if only_missing else None)
            )
        )

    # GET : construire les lignes
    for g in groups:
        group_name = g["group_name"]
        key = f"{slug}|{group_name}"

        tr = get_translation("tournament_group", key, "name", lang)
        done = bool(tr)

        if only_missing and done:
            continue

        rows.append({
            "group_name": group_name,
            "translation": tr or "",
            "done": done,
        })

    return render_template(
        "admin/translations/groups_list.html",
        lang=lang,
        only_missing=only_missing,
        tournament=tournament,
        rows=rows
    )

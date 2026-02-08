from pathlib import Path
from datetime import datetime
from shutil import copyfile

from flask import render_template, abort, request, redirect, url_for, flash, current_app
from flask_login import current_user
from flask_babel import get_locale as babel_get_locale, gettext as _

from .. import restream_bp

from app.database import get_db
from app.auth.utils import login_required
from app.permissions.decorators import role_required

from app.modules.text import slugify
from app.modules.i18n import get_translation
from app.modules.indices.registry import get_available_indices_templates, is_valid_indices_template, get_indices_template_path
from app.modules.tracker.registry import get_available_trackers, is_valid_tracker_type

from app.restream.paths import indices_sessions_dir, tracker_session_path_restream


@restream_bp.route("/manage")
@role_required("restreamer")
def manage():
    db = get_db()

    rows = db.execute(
        """
        SELECT
            r.id,
            r.slug,
            r.title,
            r.created_at,
            r.is_active,

            m.scheduled_at,
            m.is_completed,

            t.slug AS tournament_slug,
            t.name AS tournament_name,

            GROUP_CONCAT(
                CASE
                    WHEN te.name LIKE 'Solo - %'
                        THEN SUBSTR(te.name, 8)
                    ELSE te.name
                END,
                ' vs '
            ) AS teams_display

        FROM restreams r

        JOIN matches m
            ON m.id = r.match_id

        JOIN tournaments t
            ON t.id = m.tournament_id

        JOIN match_teams mt
            ON mt.match_id = m.id

        JOIN teams te
            ON te.id = mt.team_id

        GROUP BY r.id
        ORDER BY m.scheduled_at ASC
        """
    ).fetchall()

    now = datetime.utcnow()
    restreams = []
    
    lang = str(babel_get_locale() or "fr").strip().lower()

    for r in rows:
        scheduled_dt = None
        if r["scheduled_at"]:
            try:
                scheduled_dt = datetime.fromisoformat(r["scheduled_at"])
            except ValueError:
                scheduled_dt = None

        if not r["is_active"]:
            status = "inactive"
        elif scheduled_dt and scheduled_dt < now:
            status = "past"
        else:
            status = "upcoming"

        item = {
            **dict(r),
            "status": status,
            "is_active": bool(r["is_active"]),
        }

        # -------------------------------------------------
        # Traduction affichage (tournoi)
        # -------------------------------------------------
        tslug = item.get("tournament_slug")
        if tslug:
            t_tr = get_translation("tournament", tslug, "name", lang)
            if t_tr:
                item["tournament_name"] = t_tr

        restreams.append(item)


    return render_template(
        "restream/manage.html",
        restreams_manage=restreams
    )



@restream_bp.route("/create", methods=["GET", "POST"])
@login_required
@role_required("restreamer")
def create():
    db = get_db()

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------
    if request.method == "POST":
        title = request.form.get("title")
        match_id = request.form.get("match_id")
        indices_template = request.form.get("indices_template")
        tracker_type = request.form.get("tracker_type")

        twitch_url = request.form.get("twitch_url") or None
        restreamer_name = request.form.get("restreamer_name") or None
        commentator_name = request.form.get("commentator_name") or None
        tracker_name = request.form.get("tracker_name") or None

        if not title or not match_id or not indices_template or not tracker_type:
            flash(_("Tous les champs obligatoires doivent être remplis."), "error")
            return redirect(url_for("restream.create"))

        # Vérification métier : match valide et sans restream
        match = db.execute(
            """
            SELECT m.id
            FROM matches m
            LEFT JOIN restreams r ON r.match_id = m.id
            WHERE m.id = ?
              AND m.is_completed = 0
              AND m.scheduled_at IS NOT NULL
              AND m.scheduled_at >= CURRENT_TIMESTAMP
              AND r.id IS NULL
            """,
            (match_id,),
        ).fetchone()

        if not match:
            flash(_("Match invalide ou déjà associé à un restream."), "error")
            return redirect(url_for("restream.create"))

        if not is_valid_indices_template(indices_template):
            flash(_("Template d’indices invalide."), "error")
            return redirect(url_for("restream.create"))

        if not is_valid_tracker_type(tracker_type):
            flash(_("Tracker invalide."), "error")
            return redirect(url_for("restream.create"))

        slug = slugify(title)

        # --------------------------------------------------------------
        # Indices : création de la session uniquement si != "none"
        # --------------------------------------------------------------
        if indices_template != "none":
            sessions_dir = Path(current_app.instance_path) / "indices" / "sessions"
            sessions_dir.mkdir(parents=True, exist_ok=True)
            session_path = sessions_dir / f"{slug}.json"

            template_path = get_indices_template_path(indices_template)
            copyfile(template_path, session_path)

        # --------------------------------------------------------------
        # Insert DB
        # --------------------------------------------------------------
        db.execute(
            """
            INSERT INTO restreams
                (
                    slug,
                    title,
                    created_by,
                    match_id,
                    indices_template,
                    tracker_type,
                    twitch_url,
                    restreamer_name,
                    commentator_name,
                    tracker_name
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slug,
                title,
                current_user.id,
                match_id,
                indices_template,
                tracker_type,
                twitch_url,
                restreamer_name,
                commentator_name,
                tracker_name,
            ),
        )
        db.commit()

        flash(_("Restream créé avec succès."), "success")
        return redirect(url_for("restream.manage"))

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    matches = db.execute(
        """
        SELECT
            m.id,
            m.scheduled_at,
            t.slug AS tournament_slug,
            t.name AS tournament_name,
            GROUP_CONCAT(
                CASE
                    WHEN te.name LIKE 'Solo - %'
                        THEN SUBSTR(te.name, 8)
                    ELSE te.name
                END,
                ' vs '
            ) AS teams_display
        FROM matches m
        JOIN tournaments t ON t.id = m.tournament_id
        JOIN match_teams mt ON mt.match_id = m.id
        JOIN teams te ON te.id = mt.team_id
        LEFT JOIN restreams r ON r.match_id = m.id
        WHERE
            m.is_completed = 0
            AND m.scheduled_at IS NOT NULL
            AND m.scheduled_at >= CURRENT_TIMESTAMP
            AND r.id IS NULL
        GROUP BY m.id
        ORDER BY m.scheduled_at ASC
        """
    ).fetchall()
    
    # -------------------------------------------------
    # Traductions affichage (tournoi)
    # -------------------------------------------------
    lang = str(babel_get_locale() or "fr").strip().lower()

    matches = [dict(m) for m in matches]
    for m in matches:
        tslug = m.get("tournament_slug")
        if tslug:
            t_tr = get_translation("tournament", tslug, "name", lang)
            if t_tr:
                m["tournament_name"] = t_tr

    return render_template(
        "restream/create.html",
        matches=matches,
        available_indices_templates=get_available_indices_templates(),
        available_tracker_types=get_available_trackers(),
    )

@restream_bp.route("/<slug>/edit", methods=["GET", "POST"])
@login_required
@role_required("restreamer")
def edit(slug):
    db = get_db()

    restream = db.execute(
        """
        SELECT
            id,
            slug,
            title,
            twitch_url,
            restreamer_name,
            commentator_name,
            tracker_name,
            indices_template,
            tracker_type
        FROM restreams
        WHERE slug = ?
        """,
        (slug,),
    ).fetchone()

    if not restream:
        abort(404)

    if request.method == "POST":
        title = request.form.get("title")
        twitch_url = request.form.get("twitch_url") or None
        restreamer_name = request.form.get("restreamer_name") or None
        commentator_name = request.form.get("commentator_name") or None
        tracker_name = request.form.get("tracker_name") or None

        new_indices_template = request.form.get("indices_template")
        new_tracker_type = request.form.get("tracker_type")

        if not title or not new_indices_template or not new_tracker_type:
            flash(_("Tous les champs obligatoires doivent être remplis."), "error")
            return redirect(url_for("restream.edit", slug=slug))
            
        if not is_valid_indices_template(new_indices_template):
            flash(_("Template d’indices invalide."), "error")
            return redirect(url_for("restream.edit", slug=slug))
            
        if not is_valid_tracker_type(new_tracker_type):
            flash(_("Tracker invalide."), "error")
            return redirect(url_for("restream.edit", slug=slug))

        # --------------------------------------------------------------
        # Gestion des indices (delete & recreate)
        # --------------------------------------------------------------
        session_path = indices_sessions_dir() / f"{slug}.json"

        if new_indices_template != restream["indices_template"]:
            # supprimer l’ancienne session si elle existe
            if session_path.exists():
                session_path.unlink()

            # recréer seulement si != "none"
            if new_indices_template != "none":
                template_path = get_indices_template_path(new_indices_template)

                if not template_path.exists():
                    flash(_("Template d’indices introuvable."), "error")
                    return redirect(url_for("restream.edit", slug=slug))

                session_path.parent.mkdir(parents=True, exist_ok=True)
                copyfile(template_path, session_path)
                
        # --------------------------------------------------------------
        # Gestion du tracker (delete session si changement de type)
        # --------------------------------------------------------------
        if new_tracker_type != restream["tracker_type"]:
            tracker_session_path: Path = tracker_session_path_restream(int(restream["id"]))

            if tracker_session_path.exists():
                tracker_session_path.unlink()


        # --------------------------------------------------------------
        # Update DB
        # --------------------------------------------------------------
        db.execute(
            """
            UPDATE restreams
            SET
                title = ?,
                twitch_url = ?,
                restreamer_name = ?,
                commentator_name = ?,
                tracker_name = ?,
                indices_template = ?,
                tracker_type = ?
            WHERE slug = ?
            """,
            (
                title,
                twitch_url,
                restreamer_name,
                commentator_name,
                tracker_name,
                new_indices_template,
                new_tracker_type,
                slug,
            ),
        )
        db.commit()

        flash(_("Restream mis à jour."), "success")
        return redirect(url_for("restream.manage"))

    return render_template(
        "restream/edit.html",
        restream=restream,
        available_indices_templates=get_available_indices_templates(),
        available_tracker_types=get_available_trackers(),
    )

@restream_bp.route("/<slug>/enable", methods=["POST"])
@login_required
@role_required("restreamer")
def enable_restream(slug):
    db = get_db()

    updated = db.execute(
        """
        UPDATE restreams
        SET is_active = 1
        WHERE slug = ? AND is_active = 0
        """,
        (slug,)
    ).rowcount

    if not updated:
        abort(404)
        
    db.commit()
    
    # Recréation du fichier d’indices à partir du template
    restream = db.execute(
        "SELECT indices_template FROM restreams WHERE slug = ?",
        (slug,)
    ).fetchone()

    if not restream:
        abort(404)

    if restream["indices_template"] != "none":
        template_path = get_indices_template_path(restream["indices_template"])        
        session_path = indices_sessions_dir() / f"{slug}.json"
        session_path.parent.mkdir(parents=True, exist_ok=True)
        copyfile(template_path, session_path)


    flash(_("Restream réactivé."), "success")
    return redirect(url_for("restream.manage"))



@restream_bp.route("/<slug>/disable", methods=["POST"])
@login_required
@role_required("restreamer")
def disable_restream(slug):
    db = get_db()

    updated = db.execute(
        """
        UPDATE restreams
        SET is_active = 0
        WHERE slug = ? AND is_active = 1
        """,
        (slug,)
    ).rowcount

    if not updated:
        abort(404)
        
    db.commit()
    
    # Suppression du fichier d’indices si présent
    session_file = indices_sessions_dir() / f"{slug}.json"
    if session_file.exists():
        session_file.unlink()


    flash(_("Restream désactivé."), "success")
    return redirect(url_for("restream.manage"))

import json

from flask import (
    request,
    redirect,
    url_for,
    flash,
)
from app.auth.utils import login_required
from flask_babel import _

from .. import admin_bp
from app.database import get_db
from app.permissions.decorators import role_required

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
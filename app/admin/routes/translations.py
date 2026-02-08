import json

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
from app.modules.i18n import get_translation

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

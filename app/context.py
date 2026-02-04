# app/context.py

from app.database import get_db
from flask import current_app
from flask_babel import get_locale
from app.modules.i18n import get_translation

def inject_tournaments():
    db = get_db()

    internal_rows = db.execute(
        """
        SELECT
            slug,
            name,
            status
        FROM tournaments
        WHERE source = 'internal'
          AND UPPER(TRIM(name)) NOT LIKE '[CASUAL%'
        """
    ).fetchall()

    internal = []
    lang = str(get_locale() or "fr").lower()
    for t in internal_rows:
        status = t["status"]
        slug = t["slug"]
        name_db = t["name"]

        name_tr = get_translation("tournament", slug, "name", lang)
        display_name = name_tr if name_tr else name_db
        if status == "draft":
            status = "upcoming"

        internal.append(
            {
                "slug": slug,
                "name": name_db,                 # garde la source DB
                "display_name": display_name,    # nouveau champ pour l’UI
                "status": status,
            }
        )

    external = []
    for t in current_app.config.get("TOURNAMENTS", []):
        t = dict(t)
        t.setdefault("display_name", t.get("name"))
        external.append(t)
    tournaments = internal + external

    # ------------------------------------------------------------------
    # Tri stable (au minimum), pour éviter un ordre “random”
    # ------------------------------------------------------------------
    def by_name(x):
        return (x.get("display_name") or x.get("name") or "").lower()

    active_all = sorted([t for t in tournaments if t.get("status") == "active"], key=by_name)
    upcoming_all = sorted([t for t in tournaments if t.get("status") == "upcoming"], key=by_name)
    finished_all = sorted([t for t in tournaments if t.get("status") == "finished"], key=by_name)

    # ------------------------------------------------------------------
    # Limites navbar (évite le menu déroulant infini)
    # ------------------------------------------------------------------
    nav_upcoming_limit = current_app.config.get("NAV_UPCOMING_TOURNAMENTS_LIMIT", 5)

    upcoming_nav = upcoming_all[:nav_upcoming_limit]
    upcoming_more = max(0, len(upcoming_all) - len(upcoming_nav))

    return {
        # Utilisés par la navbar (dropdown)
        "tournaments_active": active_all,
        "tournaments_upcoming": upcoming_nav,
        "tournaments_upcoming_more": upcoming_more,

        # Réservés pour /tournaments plus tard (listing complet)
        "tournaments_active_all": active_all,
        "tournaments_upcoming_all": upcoming_all,
        "tournaments_finished_all": finished_all,

        # Compat: si un vieux template utilise encore tournaments_finished
        "tournaments_finished": finished_all,
    }


def inject_restreams():
    db = get_db()

    restreams = db.execute(
        """
        SELECT
            r.slug,
            r.title,
            m.scheduled_at
        FROM restreams r
        JOIN matches m
            ON m.id = r.match_id
        WHERE
            r.is_active = 1
            AND m.scheduled_at IS NOT NULL
            -- datetime('now') est une fonction SQLite
            AND m.scheduled_at >= datetime('now')
        ORDER BY m.scheduled_at ASC
        """
    ).fetchall()

    return dict(restreams=restreams)

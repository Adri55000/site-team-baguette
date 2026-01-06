# app/context.py

from app.database import get_db
from flask import current_app

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
    for t in internal_rows:
        status = t["status"]
        if status == "draft":
            status = "upcoming"

        internal.append({
            "slug": t["slug"],
            "name": t["name"],
            "status": status,
        })

    external = current_app.config.get("TOURNAMENTS", [])
    tournaments = internal + external

    return {
        "tournaments_active": [t for t in tournaments if t["status"] == "active"],
        "tournaments_upcoming": [t for t in tournaments if t["status"] == "upcoming"],
        "tournaments_finished": [t for t in tournaments if t["status"] == "finished"],
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

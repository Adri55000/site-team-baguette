def get_active_restream_by_slug(db, slug: str):
    return db.execute(
        """
        SELECT
            id,
            slug,
            title,
            match_id,
            is_active,
            tracker_type
        FROM restreams
        WHERE slug = ? AND is_active = 1
        """,
        (slug,),
    ).fetchone()

def get_match_teams(db, match_id: int):
    return db.execute(
        """
        SELECT t.id AS team_id, t.name AS team_name
        FROM match_teams mt
        JOIN teams t ON t.id = mt.team_id
        WHERE mt.match_id = ?
        ORDER BY mt.team_id ASC
        """,
        (match_id,),
    ).fetchall()
    
def get_next_planned_match_for_overlay(db, *, tournament_id=None, exclude_match_id=None):
    where = [
        "m.scheduled_at IS NOT NULL",
        "m.scheduled_at >= datetime('now')",
    ]
    params = []

    if tournament_id is not None:
        where.append("m.tournament_id = ?")
        params.append(tournament_id)

    if exclude_match_id is not None:
        where.append("m.id != ?")
        params.append(exclude_match_id)

    where_sql = " AND ".join(where)

    row = db.execute(
        f"""
        SELECT
            m.id AS match_id,
            m.scheduled_at,
            t.name AS tournament_name,
            s.stage AS series_stage,
            p.name AS phase_name,
            r.slug AS restream_slug,
            r.title AS restream_title
        FROM matches m
        JOIN tournaments t ON t.id = m.tournament_id
        LEFT JOIN series s ON s.id = m.series_id
        LEFT JOIN tournament_phases p ON p.id = s.phase_id
        JOIN restreams r
          ON r.match_id = m.id
         AND r.is_active = 1
        WHERE {where_sql}
        ORDER BY m.scheduled_at ASC
        LIMIT 1
        """,
        params,
    ).fetchone()

    if not row:
        return None

    teams = get_match_teams(db, int(row["match_id"]))  # ou _get_match_teams selon ton fichier
    team_names = [(t["team_name"] or "").replace("Solo - ", "") for t in teams]
    team_names = [n for n in team_names if n]

    result = dict(row)
    result["teams"] = teams
    result["teams_label"] = " vs ".join(team_names) if team_names else None
    return result



import re

def simplify_restream_title(title: str) -> str:
    if not title:
        return ""
    # coupe au premier ":" ou "-" (avec espaces optionnels autour)
    parts = re.split(r"\s*[:\-]\s*", title, maxsplit=1)
    return parts[0].strip()


def split_commentators(raw: str | None):
    if not raw:
        return ("", "")
    parts = re.split(r"\s*(?:,|-|\bet\b)\s*", raw, maxsplit=1)
    c1 = parts[0].strip() if len(parts) > 0 else ""
    c2 = parts[1].strip() if len(parts) > 1 else ""
    return (c1, c2)
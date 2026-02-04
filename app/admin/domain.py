# app/admin/domain.py
from flask_babel import gettext as _

def can_delete_player(conn, player_id):
    # Cas 1 : équipe multi-joueurs
    in_multi_team = conn.execute("""
        SELECT 1
        FROM team_players tp
        WHERE tp.player_id = ?
          AND tp.team_id IN (
              SELECT team_id
              FROM team_players
              GROUP BY team_id
              HAVING COUNT(*) > 1
          )
        LIMIT 1
    """, (player_id,)).fetchone()

    if in_multi_team:
        return False, _("Impossible de supprimer ce joueur : il fait partie d’une équipe multi-joueurs.")

    # Cas 2 : utilisé dans un match
    used_in_match = conn.execute("""
        SELECT 1
        FROM team_players tp
        JOIN match_teams mt ON mt.team_id = tp.team_id
        WHERE tp.player_id = ?
        LIMIT 1
    """, (player_id,)).fetchone()

    if used_in_match:
        return False, _("Impossible de supprimer ce joueur : il est utilisé dans des matchs.")

    return True, None

def can_delete_team(conn, team_id):
    used = conn.execute("""
        SELECT 1 FROM match_teams WHERE team_id = ? LIMIT 1
    """, (team_id,)).fetchone()

    if used:
        return False, _("Impossible de supprimer cette équipe : elle est utilisée dans des matchs.")

    return True, None

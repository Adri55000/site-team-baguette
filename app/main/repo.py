from app.database import get_db

def get_user_by_id(user_id):
    db = get_db()
    return db.execute(
        """
        SELECT username, role, created_at, last_login,
               avatar_filename, description, social_links
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()

def get_user_by_username(username):
    db = get_db()
    return db.execute(
        """
        SELECT id FROM users WHERE username = ?
        """,
        (username,)
    ).fetchone()

def update_user_infos(user_id, description, social_links):
    db = get_db()
    db.execute(
        """
        UPDATE users
        SET description = ?, social_links = ?
        WHERE id = ?
        """,
        (description, social_links, user_id)
    )
    db.commit()

def get_user_password_hash(user_id):
    db = get_db()
    return db.execute(
        """
        SELECT password_hash FROM users WHERE id = ?
        """,
        (user_id,)
    ).fetchone()

def update_user_password(user_id, new_password_hash):
    db = get_db()
    db.execute(
        """
        UPDATE users SET password_hash = ? WHERE id = ?
        """,
        (new_password_hash, user_id)
    )
    db.commit()

def get_internal_tournament_by_slug(slug):
    db = get_db()
    return db.execute(
        """
        SELECT
            t.id,
            t.name,
            t.slug,
            t.status,
            t.metadata,
            t.created_at,
            g.name AS game_name
        FROM tournaments t
        LEFT JOIN games g ON g.id = t.game_id
        WHERE t.slug = ?
          AND t.source = 'internal'
        """,
        (slug,)
    ).fetchone()

def get_teams_by_tournament_id(tournament_id):
    db = get_db()
    return db.execute(
            """
            SELECT DISTINCT tm.id, tm.name
            FROM teams tm
            JOIN match_teams mt ON mt.team_id = tm.id
            JOIN matches m ON m.id = mt.match_id
            WHERE m.tournament_id = ?
            ORDER BY tm.name ASC
            """,
            (tournament_id,)
        ).fetchall()

def get_phases_by_tournament_id(tournament_id):
    db = get_db()
    return db.execute(
        """
        SELECT
            id,
            name,
            type,
            position,
            details
        FROM tournament_phases
        WHERE tournament_id = ?
        ORDER BY position ASC
        """,
        (tournament_id,)
    ).fetchall()

def get_series_by_phases_ids(phase_ids, placeholders):
    db = get_db()
    return db.execute(
            f"""
            SELECT
                s.id,
                s.phase_id,
                s.stage,
                s.team1_id,
                s.team2_id,
                tw.name AS winner_name
            FROM series s
            LEFT JOIN teams tw ON tw.id = s.winner_team_id
            WHERE s.phase_id IN ({placeholders})
            ORDER BY s.id ASC
            """,
            phase_ids
        ).fetchall()

def get_teams_by_series_ids(series_ids,placeholders):
    db = get_db()
    return db.execute(
            f"""
            SELECT DISTINCT
                m.series_id,
                tm.name AS team_name
            FROM matches m
            JOIN match_teams mt ON mt.match_id = m.id
            JOIN teams tm ON tm.id = mt.team_id
            WHERE m.series_id IN ({placeholders})
            ORDER BY tm.name ASC
            """,
            series_ids
        ).fetchall()

def get_scores_by_series_ids(series_ids, placeholders):
    db = get_db()
    return db.execute(
            f"""
            SELECT
                s.id AS series_id,

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
            LEFT JOIN matches m
                ON m.series_id = s.id
                AND m.is_completed = 1
            LEFT JOIN match_teams mt
                ON mt.match_id = m.id
            WHERE s.id IN ({placeholders})
            GROUP BY s.id
            """,
            series_ids
        ).fetchall()

def get_tiebreaks_by_tournament(tournament_id):
    db = get_db()
    return db.execute(
        """
        SELECT id, is_completed
        FROM matches
        WHERE tournament_id = ?
          AND series_id IS NULL
        ORDER BY id ASC
        """,
        (tournament_id,)
    ).fetchall()

def get_teams_by_matches_ids(match_ids, placeholders):
    db = get_db()
    return db.execute(
            f"""
            SELECT
                mt.match_id,
                tm.name AS team_name
            FROM match_teams mt
            JOIN teams tm ON tm.id = mt.team_id
            WHERE mt.match_id IN ({placeholders})
            ORDER BY mt.team_id ASC
            """,
            match_ids
        ).fetchall()

def get_groupteams_by_tournament_id(tournament_id):
    db = get_db()
    return db.execute(
                """
                SELECT
                    tt.team_id,
                    tm.name AS team_name,
                    tt.group_name,
                    tt.seed,
                    tt.position
                FROM tournament_teams tt
                JOIN teams tm ON tm.id = tt.team_id
                WHERE tt.tournament_id = ?
                  AND tt.group_name IS NOT NULL
                  AND TRIM(tt.group_name) != ''
                ORDER BY tt.group_name COLLATE NOCASE, tm.name COLLATE NOCASE
                """,
                (tournament_id,)
            ).fetchall()

def get_winnerteams_by_phase_id(phase_id):
    db = get_db()
    return db.execute(
                """
                SELECT
                    winner_team_id AS team_id,
                    COUNT(*) AS wins
                FROM series
                WHERE phase_id = ?
                  AND winner_team_id IS NOT NULL
                GROUP BY winner_team_id
                """,
                (phase_id,)
            ).fetchall()

def get_playedmatches_by_phase_id(phase_id):
    db = get_db()
    return db.execute(
                """
                SELECT
                    x.team_id,
                    COUNT(*) AS played
                FROM (
                    SELECT team1_id AS team_id
                    FROM series
                    WHERE phase_id = ?
                      AND team1_id IS NOT NULL
                      AND team2_id IS NOT NULL
                    UNION ALL
                    SELECT team2_id AS team_id
                    FROM series
                    WHERE phase_id = ?
                      AND team1_id IS NOT NULL
                      AND team2_id IS NOT NULL
                ) x
                GROUP BY x.team_id
                """,
                (phase_id, phase_id)
            ).fetchall()

def get_bracketseries_by_phase_id(phase_id):
    db = get_db()
    return db.execute(
                """
                SELECT
                    s.id,
                    s.round,
                    s.stage,
                    s.best_of,
                    s.team1_id,
                    s.team2_id,
                    t1.name AS team1_name,
                    t2.name AS team2_name,
                    s.source_team1_series_id,
                    s.source_team1_type,
                    s.source_team2_series_id,
                    s.source_team2_type,
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
                LEFT JOIN teams t1 ON t1.id = s.team1_id
                LEFT JOIN teams t2 ON t2.id = s.team2_id
                LEFT JOIN matches m
                    ON m.series_id = s.id
                    AND m.is_completed = 1
                LEFT JOIN match_teams mt
                    ON mt.match_id = m.id
                WHERE s.phase_id = ?
                GROUP BY s.id
                ORDER BY s.round ASC, s.stage ASC
                """,
                (phase_id,)
            ).fetchall()

def get_tournaments():
    db = get_db()
    return db.execute(
        """
        SELECT
            t.id,
            t.name,
            t.slug,
            t.status,
            t.game_id,
            g.name AS game_name,
            MAX(m.scheduled_at) AS last_match_at
        FROM tournaments t
        LEFT JOIN games g
            ON g.id = t.game_id
        LEFT JOIN matches m
            ON m.tournament_id = t.id
        WHERE t.source = 'internal'
          AND UPPER(TRIM(t.name)) NOT LIKE '[CASUAL%'
        GROUP BY t.id
        """
    ).fetchall()
BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,       -- ex : "Zelda: ALTTPR"
    short_name TEXT NOT NULL UNIQUE, -- ex : "ALTTPR"
    icon_path TEXT,                  -- optionnel : "/static/img/games/alttp.png"
    color TEXT                       -- optionnel : "#4CAF50", pour les tags
);
CREATE TABLE IF NOT EXISTS match_teams (
    match_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,

    position INTEGER,              -- nullable
    final_time INTEGER,
    final_time_raw TEXT,
    is_winner INTEGER DEFAULT 0,

    PRIMARY KEY(match_id, team_id),

    FOREIGN KEY(match_id) REFERENCES matches(id) ON DELETE CASCADE,
    FOREIGN KEY(team_id) REFERENCES teams(id)
);
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    series_id INTEGER,        -- NULL = match indépendant (FFA possible)
    match_index INTEGER,      -- position dans la série, 1,2,3...

    scheduled_at TEXT,
    completed INTEGER DEFAULT 0, tournament_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, is_completed INTEGER DEFAULT 0,

    FOREIGN KEY(series_id) REFERENCES series(id)
);
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    user_id INTEGER,   -- optionnel : lien avec table users
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(user_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS restreams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER NOT NULL,

    match_id INTEGER NOT NULL UNIQUE,

    indices_template TEXT NOT NULL,
    twitch_url TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,

    FOREIGN KEY (created_by) REFERENCES users(id),
    FOREIGN KEY (match_id) REFERENCES matches(id)
);
CREATE TABLE IF NOT EXISTS series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,

    team1_id INTEGER NOT NULL,
    team2_id INTEGER NOT NULL,

    stage TEXT,              -- nom de la phase (ex : "Quarterfinal", "Group A - Match 3")
    best_of INTEGER NOT NULL DEFAULT 1,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP, winner_team_id INTEGER, phase_id INTEGER
REFERENCES tournament_phases(id), source_team1_series_id INTEGER NULL, source_team2_series_id INTEGER NULL, source_team1_type TEXT NULL, source_team2_type TEXT NULL, bracket_position TEXT NULL,

    FOREIGN KEY(tournament_id) REFERENCES tournaments(id),
    FOREIGN KEY(team1_id) REFERENCES teams(id),
    FOREIGN KEY(team2_id) REFERENCES teams(id)
);
CREATE TABLE IF NOT EXISTS team_players (
    team_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    position INTEGER DEFAULT 1,

    PRIMARY KEY(team_id, player_id),

    FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY(player_id) REFERENCES players(id)
);
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    tournament_id INTEGER,   -- NULL = team solo globale

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(tournament_id) REFERENCES tournaments(id)
);
CREATE TABLE IF NOT EXISTS tournament_phases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    tournament_id INTEGER NOT NULL,
    position INTEGER NOT NULL,

    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'custom',

    created_at TEXT DEFAULT CURRENT_TIMESTAMP, details TEXT NULL,

    FOREIGN KEY (tournament_id) REFERENCES tournaments(id)
);
CREATE TABLE IF NOT EXISTS tournament_teams (
    tournament_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,

    -- m�tadonn�es d�inscription (extensibles)
    seed INTEGER,              -- optionnel (t�tes de s�rie)
    group_name TEXT,           -- ex: "Group A"
    position INTEGER,          -- position dans un groupe ou classement

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (tournament_id, team_id),

    FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES teams(id)
);
CREATE TABLE IF NOT EXISTS tournaments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL,    -- 'upcoming', 'active', 'finished'
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
, game_id INTEGER REFERENCES games(id), source TEXT NOT NULL DEFAULT 'internal', metadata TEXT, slug TEXT);
CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'invité',
        is_active INTEGER NOT NULL DEFAULT 1,
        description TEXT,
        avatar_filename TEXT,
        social_links TEXT,
        last_login TEXT,
        created_at TEXT NOT NULL
    );
CREATE UNIQUE INDEX idx_tournaments_slug
ON tournaments(slug);
CREATE TRIGGER create_solo_team_after_player_insert
AFTER INSERT ON players
BEGIN
    INSERT INTO teams (name, tournament_id)
    VALUES ('Solo - ' || NEW.name, NULL);

    INSERT INTO team_players (team_id, player_id)
    VALUES (
        (SELECT id FROM teams WHERE name = 'Solo - ' || NEW.name LIMIT 1),
        NEW.id
    );
END;
COMMIT;

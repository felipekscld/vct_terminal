"""SQLite schema definitions and migrations."""

from __future__ import annotations

from src.db.connection import get_db

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    region          TEXT,
    tier            TEXT,
    status          TEXT,
    start_date      TEXT,
    end_date        TEXT,
    prize           TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS stages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        INTEGER NOT NULL REFERENCES events(id),
    name            TEXT NOT NULL,
    UNIQUE(event_id, name)
);

CREATE TABLE IF NOT EXISTS teams (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    tag             TEXT,
    country         TEXT,
    country_code    TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS matches (
    id              INTEGER PRIMARY KEY,
    event_id        INTEGER REFERENCES events(id),
    stage_id        INTEGER REFERENCES stages(id),
    stage_name      TEXT,
    phase           TEXT,
    date            TEXT,
    time            TEXT,
    bo_type         TEXT,
    patch           TEXT,
    team1_id        INTEGER REFERENCES teams(id),
    team2_id        INTEGER REFERENCES teams(id),
    score1          INTEGER,
    score2          INTEGER,
    status          TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS maps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL REFERENCES matches(id),
    game_id         TEXT,
    map_name        TEXT,
    map_order       INTEGER,
    pick_team_id    INTEGER REFERENCES teams(id),
    team1_id        INTEGER REFERENCES teams(id),
    team2_id        INTEGER REFERENCES teams(id),
    team1_score     INTEGER,
    team2_score     INTEGER,
    team1_atk_rounds    INTEGER,
    team1_def_rounds    INTEGER,
    team2_atk_rounds    INTEGER,
    team2_def_rounds    INTEGER,
    team1_start_side    TEXT,
    team1_pistols_won   INTEGER DEFAULT 0,
    team2_pistols_won   INTEGER DEFAULT 0,
    team1_pistol_conversions INTEGER DEFAULT 0,
    team2_pistol_conversions INTEGER DEFAULT 0,
    is_ot           INTEGER DEFAULT 0,
    round_diff      INTEGER,
    winner_team_id  INTEGER REFERENCES teams(id),
    UNIQUE(match_id, game_id)
);

CREATE TABLE IF NOT EXISTS rounds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    map_id          INTEGER NOT NULL REFERENCES maps(id),
    round_number    INTEGER NOT NULL,
    winner_team_id  INTEGER REFERENCES teams(id),
    winner_team_short TEXT,
    winner_side     TEXT,
    method          TEXT,
    score_t1        INTEGER,
    score_t2        INTEGER,
    UNIQUE(map_id, round_number)
);

CREATE TABLE IF NOT EXISTS map_compositions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    map_id          INTEGER NOT NULL REFERENCES maps(id),
    team_id         INTEGER NOT NULL REFERENCES teams(id),
    agent1          TEXT,
    agent2          TEXT,
    agent3          TEXT,
    agent4          TEXT,
    agent5          TEXT,
    comp_hash       TEXT,
    UNIQUE(map_id, team_id)
);

CREATE TABLE IF NOT EXISTS player_map_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    map_id          INTEGER NOT NULL REFERENCES maps(id),
    player_id       INTEGER,
    player_name     TEXT NOT NULL,
    team_id         INTEGER REFERENCES teams(id),
    agent           TEXT,
    rating          REAL,
    acs             INTEGER,
    kills           INTEGER,
    deaths          INTEGER,
    assists         INTEGER,
    kd_diff         INTEGER,
    kast            REAL,
    adr             REAL,
    hs_pct          REAL,
    fk              INTEGER,
    fd              INTEGER,
    fk_diff         INTEGER,
    UNIQUE(map_id, player_id)
);

CREATE TABLE IF NOT EXISTS pending_vetos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL REFERENCES matches(id),
    source          TEXT NOT NULL DEFAULT 'manual',
    map_order       INTEGER NOT NULL,
    action          TEXT NOT NULL,
    team_id         INTEGER REFERENCES teams(id),
    team_name       TEXT,
    map_name        TEXT NOT NULL,
    start_side      TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(match_id, map_order, action)
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL REFERENCES matches(id),
    map_id          INTEGER REFERENCES maps(id),
    map_number      INTEGER,
    bookmaker       TEXT NOT NULL,
    market_type     TEXT NOT NULL,
    selection       TEXT NOT NULL,
    odds_value      REAL NOT NULL,
    timestamp       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS placed_bets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL REFERENCES matches(id),
    map_id          INTEGER REFERENCES maps(id),
    bookmaker       TEXT NOT NULL,
    market_type     TEXT NOT NULL,
    selection       TEXT NOT NULL,
    odds_value      REAL NOT NULL,
    stake           REAL NOT NULL,
    bet_type        TEXT NOT NULL DEFAULT 'single',
    parlay_group_id TEXT,
    placed_at       TEXT DEFAULT (datetime('now')),
    result          TEXT DEFAULT 'pending',
    pnl             REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS manual_opinions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL REFERENCES matches(id),
    map_id          INTEGER REFERENCES maps(id),
    note            TEXT NOT NULL,
    confidence      TEXT,
    timestamp       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS app_config (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS live_map_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL REFERENCES matches(id),
    map_number      INTEGER NOT NULL,
    map_name        TEXT,
    winner_team_id  INTEGER REFERENCES teams(id),
    winner_team_side TEXT,
    score_a         INTEGER,
    score_b         INTEGER,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(match_id, map_number)
);

-- Indexes for frequent queries
CREATE INDEX IF NOT EXISTS idx_matches_event ON matches(event_id);
CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(team1_id, team2_id);
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);
CREATE INDEX IF NOT EXISTS idx_matches_status_date ON matches(status, date);
CREATE INDEX IF NOT EXISTS idx_maps_match ON maps(match_id);
CREATE INDEX IF NOT EXISTS idx_maps_name ON maps(map_name);
CREATE INDEX IF NOT EXISTS idx_maps_teams ON maps(team1_id, team2_id);
CREATE INDEX IF NOT EXISTS idx_rounds_map ON rounds(map_id);
CREATE INDEX IF NOT EXISTS idx_compositions_map ON map_compositions(map_id);
CREATE INDEX IF NOT EXISTS idx_compositions_team ON map_compositions(team_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_map ON player_map_stats(map_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_player ON player_map_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_odds_match ON odds_snapshots(match_id);
CREATE INDEX IF NOT EXISTS idx_odds_market ON odds_snapshots(market_type);
CREATE INDEX IF NOT EXISTS idx_vetos_match ON pending_vetos(match_id);
CREATE INDEX IF NOT EXISTS idx_bets_match ON placed_bets(match_id);
CREATE INDEX IF NOT EXISTS idx_bets_parlay ON placed_bets(parlay_group_id);
CREATE INDEX IF NOT EXISTS idx_live_results_match ON live_map_results(match_id);
CREATE INDEX IF NOT EXISTS idx_live_results_match_map ON live_map_results(match_id, map_number);
"""


def init_db() -> None:
    """Create all tables and indexes."""
    with get_db() as conn:
        conn.executescript(SCHEMA_SQL)


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")

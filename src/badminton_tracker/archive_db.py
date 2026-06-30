"""Private historical archive: SQLite schema, connection, upserts, queries.

PRIVATE store (lives under data/archive/). Holds profile GUIDs; never published.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import ARCHIVE_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS tournaments (
    id          TEXT PRIMARY KEY,
    name        TEXT,
    year        INTEGER,
    start_date  TEXT,
    end_date    TEXT,
    location    TEXT,
    region      TEXT,
    category    TEXT,
    source_url  TEXT,
    fetched_at  TEXT
);
CREATE TABLE IF NOT EXISTS draws (
    id            TEXT PRIMARY KEY,
    tournament_id TEXT REFERENCES tournaments(id),
    name          TEXT,
    draw_type     TEXT,
    ordering      INTEGER
);
CREATE TABLE IF NOT EXISTS players (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id TEXT REFERENCES tournaments(id),
    display_name  TEXT,
    profile_guid  TEXT,
    club          TEXT,
    seed          INTEGER,
    UNIQUE(tournament_id, display_name, profile_guid)
);
CREATE TABLE IF NOT EXISTS matches (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    draw_id          TEXT REFERENCES draws(id),
    round_label      TEXT,
    round_index      INTEGER,
    position         INTEGER,
    side1_player_ids TEXT,
    side2_player_ids TEXT,
    score_raw        TEXT,
    winner_side      INTEGER,
    scheduled_iso    TEXT,
    court            TEXT
);
CREATE TABLE IF NOT EXISTS crawl_state (
    tournament_id TEXT PRIMARY KEY REFERENCES tournaments(id),
    status        TEXT,
    attempts      INTEGER DEFAULT 0,
    last_error    TEXT,
    updated_at    TEXT
);
CREATE TABLE IF NOT EXISTS raw_cache (
    url_hash    TEXT PRIMARY KEY,
    url         TEXT,
    body_path   TEXT,
    status_code INTEGER,
    fetched_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_draws_tournament ON draws(tournament_id);
CREATE INDEX IF NOT EXISTS idx_players_tournament ON players(tournament_id);
CREATE INDEX IF NOT EXISTS idx_matches_draw ON matches(draw_id);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else ARCHIVE_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn

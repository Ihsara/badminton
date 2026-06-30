"""Private historical archive: SQLite schema, connection, upserts, queries.

PRIVATE store (lives under data/archive/). Holds profile GUIDs; never published.
"""

from __future__ import annotations

import json
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


def upsert_tournament(conn: sqlite3.Connection, t: dict) -> None:
    conn.execute(
        """INSERT INTO tournaments
           (id,name,year,start_date,end_date,location,region,category,source_url,
            fetched_at)
           VALUES (:id,:name,:year,:start_date,:end_date,:location,:region,:category,
                   :source_url,:fetched_at)
           ON CONFLICT(id) DO UPDATE SET
             name=excluded.name, year=excluded.year, start_date=excluded.start_date,
             end_date=excluded.end_date, location=excluded.location, region=excluded.region,
             category=excluded.category, source_url=excluded.source_url,
             fetched_at=excluded.fetched_at""",
        t,
    )
    conn.commit()


def upsert_draw(conn: sqlite3.Connection, d: dict) -> None:
    conn.execute(
        """INSERT INTO draws (id,tournament_id,name,draw_type,ordering)
           VALUES (:id,:tournament_id,:name,:draw_type,:ordering)
           ON CONFLICT(id) DO UPDATE SET
             tournament_id=excluded.tournament_id, name=excluded.name,
             draw_type=excluded.draw_type, ordering=excluded.ordering""",
        d,
    )
    conn.commit()


def upsert_player(conn: sqlite3.Connection, p: dict) -> int:
    conn.execute(
        """INSERT INTO players (tournament_id,display_name,profile_guid,club,seed)
           VALUES (:tournament_id,:display_name,:profile_guid,:club,:seed)
           ON CONFLICT(tournament_id,display_name,profile_guid)
           DO UPDATE SET club=excluded.club, seed=excluded.seed""",
        p,
    )
    conn.commit()
    row = conn.execute(
        """SELECT id FROM players
           WHERE tournament_id=:tournament_id AND display_name=:display_name
             AND (profile_guid IS :profile_guid OR profile_guid = :profile_guid)""",
        p,
    ).fetchone()
    return int(row["id"])


def insert_match(conn: sqlite3.Connection, m: dict) -> None:
    payload = dict(m)
    payload["side1_player_ids"] = json.dumps(m["side1_player_ids"])
    payload["side2_player_ids"] = json.dumps(m["side2_player_ids"])
    conn.execute(
        """INSERT INTO matches
           (draw_id,round_label,round_index,position,side1_player_ids,
            side2_player_ids,score_raw,winner_side,scheduled_iso,court)
           VALUES (:draw_id,:round_label,:round_index,:position,:side1_player_ids,
                   :side2_player_ids,:score_raw,:winner_side,:scheduled_iso,:court)""",
        payload,
    )
    conn.commit()


def set_state(
    conn: sqlite3.Connection, tournament_id: str, status: str,
    *, error: str | None = None, now: str,
) -> None:
    bump = 1 if status == "error" else 0
    conn.execute(
        """INSERT INTO crawl_state (tournament_id,status,attempts,last_error,updated_at)
           VALUES (:tid,:status,:bump,:err,:now)
           ON CONFLICT(tournament_id) DO UPDATE SET
             status=excluded.status,
             attempts=crawl_state.attempts + :bump,
             last_error=excluded.last_error,
             updated_at=excluded.updated_at""",
        {"tid": tournament_id, "status": status, "bump": bump,
         "err": error, "now": now},
    )
    conn.commit()


def pending_tournaments(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """SELECT t.id FROM tournaments t
           LEFT JOIN crawl_state s ON s.tournament_id = t.id
           WHERE s.status IS NULL OR s.status != 'done'
           ORDER BY t.id"""
    ).fetchall()
    return [r["id"] for r in rows]

# Private Archive Crawler + SQLite Store — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete, private, queryable SQLite archive of Finnish badminton (`badmintonfinland.tournamentsoftware.com`) from 2020→now — every tournament, draw, match, player, with full bracket structure preserved — accessible only through the authed backend, leaving the public site untouched.

**Architecture:** Four isolated layers — `enumerate` (year-range tournament list) → `fetch+raw-cache` (content-addressed disk cache, throttled, resumable) → `parse` (pure HTML→dict, no network, fixture-tested) → `store` (normalized SQLite + `crawl_state` checkpoints). A resumable state machine drives per-tournament progress. Authed `/api/archive/*` endpoints read the DB only when the server is on and `BADMINTON_EDIT_PASSWORD` is set.

**Tech Stack:** Python (managed via `uv`), stdlib `sqlite3`, stdlib `html.parser` (extends existing `_DrawParser`), Playwright (existing `client.py`), FastAPI (existing `server.py`), `pytest`, `ruff`.

## Global Constraints

- **uv only** — never bare `pip`/`python`. Run via `uv run ...`. The agent's shell may need the full path `~/.local/bin/uv.exe`.
- **ruff clean** — `uv run ruff check` must pass before any task is considered done.
- **PRIVACY IS THE ARCHITECTURE (rule #4).** The archive DB + raw cache live ONLY under `data/archive/` (inside the private nested repo, gitignored by the public repo). NEVER `git add` anything under `data/`. Profile GUIDs may live in the private DB but must NEVER reach `web/*.json` or the public repo. The *tournament* GUID is a public id and is allowed.
- **Public pipeline untouched.** Nothing in `build.py`/`export.py`/`web/` may read the archive. `web/data.json` and `web/upcoming.json` must stay byte-for-byte unaffected.
- **No cross-tournament person-merging here.** `players` is per-tournament. All identity merging is deferred to sub-project D (`2026-06-28-multi-nickname-identity-and-name-discovery`).
- **Politeness.** Concurrency 1; configurable inter-request delay (default ≥700 ms, matching the existing upcoming pipeline); exponential backoff on errors.
- **TDD.** Write the failing test first, watch it fail, implement minimally, watch it pass, commit.

## File Structure

| File | Responsibility |
|------|----------------|
| `src/badminton_tracker/archive_db.py` | SQLite schema creation, connection, upsert helpers, queries |
| `src/badminton_tracker/archive_enumerate.py` | Pure parser + driver for year-range tournament enumeration |
| `src/badminton_tracker/archive_parse.py` | Pure HTML→dict parsers for draw lists + full brackets |
| `src/badminton_tracker/archive_fetch.py` | Fetch + raw-cache (uses `client.py`), throttle/backoff |
| `src/badminton_tracker/archive_crawl.py` | State-machine run loop tying the layers together |
| `src/badminton_tracker/config.py` (modify) | Add `ARCHIVE_DIR`, `ARCHIVE_DB`, `ARCHIVE_RAW_DIR` paths |
| `src/badminton_tracker/server.py` (modify) | Add authed `/api/archive/*` read endpoints |
| `src/badminton_tracker/__main__.py` (modify) | Add `archive-crawl` subcommand |
| `tests/test_archive_db.py` | Schema + upsert + query tests |
| `tests/test_archive_enumerate.py` | Enumeration parser tests (fixtures) |
| `tests/test_archive_parse.py` | Bracket/draw parser tests (fixtures) |
| `tests/test_archive_crawl.py` | State-machine resume/idempotency tests (fake client) |
| `tests/test_archive_privacy.py` | Privacy-guard assertions |
| `tests/fixtures/archive/*.html` | Saved HTML fixtures |

---

### Task 1: Config paths for the private archive

**Files:**
- Modify: `src/badminton_tracker/config.py`
- Test: `tests/test_archive_db.py`

**Interfaces:**
- Produces: `ARCHIVE_DIR: Path`, `ARCHIVE_DB: Path`, `ARCHIVE_RAW_DIR: Path` (all under `DATA_DIR / "archive"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_archive_db.py
from badminton_tracker import config


def test_archive_paths_live_under_private_data_dir():
    assert config.ARCHIVE_DIR == config.DATA_DIR / "archive"
    assert config.ARCHIVE_DB == config.ARCHIVE_DIR / "archive.sqlite"
    assert config.ARCHIVE_RAW_DIR == config.ARCHIVE_DIR / "raw"
    # Must be inside the private data repo, never the public web dir.
    assert config.DATA_DIR in config.ARCHIVE_DB.parents
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_archive_db.py::test_archive_paths_live_under_private_data_dir -v`
Expected: FAIL with `AttributeError: module 'badminton_tracker.config' has no attribute 'ARCHIVE_DIR'`

- [ ] **Step 3: Add the paths to config.py**

Add after the identity-model block (around line 40):

```python
# ── Private historical archive (sub-project A) ─────────────────────────────
# Site-wide 2020→now archive. PRIVATE: lives in the data/ repo, gitignored by
# the public repo. Holds profile GUIDs — never published to web/*.json.
ARCHIVE_DIR = DATA_DIR / "archive"
ARCHIVE_DB = ARCHIVE_DIR / "archive.sqlite"
ARCHIVE_RAW_DIR = ARCHIVE_DIR / "raw"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_archive_db.py::test_archive_paths_live_under_private_data_dir -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/badminton_tracker/config.py tests/test_archive_db.py
git commit -m "feat(archive): private archive config paths"
```

---

### Task 2: SQLite schema + connection

**Files:**
- Create: `src/badminton_tracker/archive_db.py`
- Test: `tests/test_archive_db.py`

**Interfaces:**
- Consumes: `config.ARCHIVE_DB`, `config.ARCHIVE_DIR`.
- Produces:
  - `connect(db_path: Path | None = None) -> sqlite3.Connection` — opens (creating parent dir), enables foreign keys, creates schema if missing, returns connection with `row_factory = sqlite3.Row`.
  - `SCHEMA: str` — the full DDL.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_archive_db.py  (append)
from badminton_tracker import archive_db


def test_connect_creates_all_tables(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")
    names = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"tournaments", "draws", "players", "matches",
            "crawl_state", "raw_cache"} <= names
    conn.close()


def test_connect_enables_foreign_keys(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_archive_db.py::test_connect_creates_all_tables -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'badminton_tracker.archive_db'`

- [ ] **Step 3: Write archive_db.py**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_archive_db.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/badminton_tracker/archive_db.py tests/test_archive_db.py
git commit -m "feat(archive): SQLite schema + connection"
```

---

### Task 3: Upsert helpers + checkpoint

**Files:**
- Modify: `src/badminton_tracker/archive_db.py`
- Test: `tests/test_archive_db.py`

**Interfaces:**
- Produces:
  - `upsert_tournament(conn, t: dict) -> None` — keys: `id,name,year,start_date,end_date,location,region,category,source_url,fetched_at`.
  - `upsert_draw(conn, d: dict) -> None` — keys: `id,tournament_id,name,draw_type,ordering`.
  - `upsert_player(conn, p: dict) -> int` — keys: `tournament_id,display_name,profile_guid,club,seed`; returns the player row id (idempotent via UNIQUE).
  - `insert_match(conn, m: dict) -> None` — keys match `matches` columns; `side1_player_ids`/`side2_player_ids` are Python lists, stored as JSON.
  - `set_state(conn, tournament_id: str, status: str, *, error: str | None = None, now: str) -> None` — upserts `crawl_state`, increments `attempts` when status is `error`.
  - `pending_tournaments(conn) -> list[str]` — tournament ids whose status is not `done`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_archive_db.py  (append)
def test_upsert_player_is_idempotent(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")
    archive_db.upsert_tournament(conn, {
        "id": "T1", "name": "Cup", "year": 2024, "start_date": None,
        "end_date": None, "location": None, "region": None, "category": None,
        "source_url": None, "fetched_at": "2026-06-30"})
    p = {"tournament_id": "T1", "display_name": "Jane Doe",
         "profile_guid": "G1", "club": None, "seed": None}
    a = archive_db.upsert_player(conn, p)
    b = archive_db.upsert_player(conn, p)
    assert a == b
    n = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    assert n == 1
    conn.close()


def test_insert_match_stores_player_id_lists_as_json(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")
    archive_db.upsert_tournament(conn, {
        "id": "T1", "name": "Cup", "year": 2024, "start_date": None,
        "end_date": None, "location": None, "region": None, "category": None,
        "source_url": None, "fetched_at": "x"})
    archive_db.upsert_draw(conn, {
        "id": "D1", "tournament_id": "T1", "name": "MD", "draw_type": "elimination",
        "ordering": 0})
    archive_db.insert_match(conn, {
        "draw_id": "D1", "round_label": "Final", "round_index": 0, "position": 0,
        "side1_player_ids": [1, 2], "side2_player_ids": [3, 4],
        "score_raw": "21-15 21-18", "winner_side": 1,
        "scheduled_iso": None, "court": None})
    row = conn.execute("SELECT side1_player_ids FROM matches").fetchone()
    import json
    assert json.loads(row[0]) == [1, 2]
    conn.close()


def test_set_state_and_pending(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")
    for tid in ("T1", "T2"):
        archive_db.upsert_tournament(conn, {
            "id": tid, "name": tid, "year": 2024, "start_date": None,
            "end_date": None, "location": None, "region": None,
            "category": None, "source_url": None, "fetched_at": "x"})
    archive_db.set_state(conn, "T1", "pending", now="t")
    archive_db.set_state(conn, "T2", "done", now="t")
    assert archive_db.pending_tournaments(conn) == ["T1"]
    archive_db.set_state(conn, "T1", "error", error="boom", now="t")
    row = conn.execute(
        "SELECT attempts, last_error FROM crawl_state WHERE tournament_id='T1'"
    ).fetchone()
    assert row["attempts"] == 1 and row["last_error"] == "boom"
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_archive_db.py::test_upsert_player_is_idempotent -v`
Expected: FAIL with `AttributeError: module 'badminton_tracker.archive_db' has no attribute 'upsert_tournament'`

- [ ] **Step 3: Add the helpers to archive_db.py**

```python
def upsert_tournament(conn: sqlite3.Connection, t: dict) -> None:
    conn.execute(
        """INSERT INTO tournaments
           (id,name,year,start_date,end_date,location,region,category,source_url,fetched_at)
           VALUES (:id,:name,:year,:start_date,:end_date,:location,:region,:category,:source_url,:fetched_at)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_archive_db.py -v`
Expected: PASS (all)

- [ ] **Step 5: ruff + commit**

```bash
uv run ruff check src/badminton_tracker/archive_db.py
git add src/badminton_tracker/archive_db.py tests/test_archive_db.py
git commit -m "feat(archive): upsert helpers + crawl-state checkpoints"
```

---

### Task 4: Tournament enumeration parser

**Files:**
- Create: `src/badminton_tracker/archive_enumerate.py`
- Test: `tests/test_archive_enumerate.py`
- Test fixture: `tests/fixtures/archive/find_tournament_page.html`

**Interfaces:**
- Consumes: nothing internal (pure parser).
- Produces: `parse_tournament_list(html: str) -> list[dict]` — returns `[{"id": guid, "name": str, "start_date": iso|None}]`, de-duped by guid (lowercased), skipping registration/empty links. Mirrors `upcoming_find._TOUR_RE` / `_date_from_name` but without the horizon filter (we want ALL tournaments).

- [ ] **Step 1: Create the fixture**

Save a small representative slice of a real `/find/tournament` result page. Minimal acceptable fixture:

```html
<!-- tests/fixtures/archive/find_tournament_page.html -->
<html><body>
<a href="/sport/tournament?id=11111111-1111-1111-1111-111111111111">Spring Open 12.4.2024</a>
<a href="/sport/tournament?id=22222222-2222-2222-2222-222222222222">Autumn Cup 3.10.2022</a>
<a href="/sport/tournament?id=11111111-1111-1111-1111-111111111111">Spring Open 12.4.2024</a>
<a href="/sport/tournament?id=33333333-3333-3333-3333-333333333333">Ilmoittautuminen</a>
</body></html>
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_archive_enumerate.py
from pathlib import Path

from badminton_tracker import archive_enumerate

FIX = Path(__file__).parent / "fixtures" / "archive" / "find_tournament_page.html"


def test_parse_tournament_list_dedupes_and_extracts_dates():
    html = FIX.read_text(encoding="utf-8")
    out = archive_enumerate.parse_tournament_list(html)
    ids = [t["id"].lower() for t in out]
    assert ids.count("11111111-1111-1111-1111-111111111111") == 1  # de-duped
    by_id = {t["id"].lower(): t for t in out}
    assert by_id["11111111-1111-1111-1111-111111111111"]["start_date"] == "2024-04-12"
    assert by_id["22222222-2222-2222-2222-222222222222"]["start_date"] == "2022-10-03"


def test_parse_tournament_list_skips_registration_links():
    html = FIX.read_text(encoding="utf-8")
    names = [t["name"].lower() for t in archive_enumerate.parse_tournament_list(html)]
    assert not any("ilmoittautu" in n for n in names)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_archive_enumerate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'badminton_tracker.archive_enumerate'`

- [ ] **Step 4: Write archive_enumerate.py**

```python
"""Enumerate ALL tournaments from /find/tournament result pages (pure parser
+ thin live driver). Unlike the upcoming finder, no horizon filter — we archive
every tournament in the requested year range."""

from __future__ import annotations

import re

_TOUR_RE = re.compile(
    r'<a[^>]*href="[^"]*/sport/tournament\?id=([0-9A-Fa-f-]{36})"[^>]*>(.*?)</a>',
    re.I | re.S,
)
_FI_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def _date_from_name(name: str) -> str | None:
    m = _FI_DATE_RE.search(name)
    if not m:
        return None
    d, mo, y = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def parse_tournament_list(html: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for m in _TOUR_RE.finditer(html):
        guid = m.group(1)
        name = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if not name or "ilmoittautu" in name.lower() or guid.lower() in seen:
            continue
        seen.add(guid.lower())
        out.append({"id": guid, "name": name, "start_date": _date_from_name(name)})
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_archive_enumerate.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: ruff + commit**

```bash
uv run ruff check src/badminton_tracker/archive_enumerate.py
git add src/badminton_tracker/archive_enumerate.py tests/test_archive_enumerate.py tests/fixtures/archive/find_tournament_page.html
git commit -m "feat(archive): tournament-list enumeration parser"
```

---

### Task 5: Bracket/draw parser

**Files:**
- Create: `src/badminton_tracker/archive_parse.py`
- Test: `tests/test_archive_parse.py`
- Test fixtures: `tests/fixtures/archive/draw_list.html`, `tests/fixtures/archive/bracket_elimination.html`

**Interfaces:**
- Consumes: nothing internal (pure parsers).
- Produces:
  - `parse_draw_list(html: str) -> list[dict]` — `[{"id": str, "name": str, "draw_type": str, "ordering": int}]` from a tournament's draws page.
  - `parse_bracket(html: str) -> list[dict]` — one dict per match: `{"round_label","round_index","position","sides":[[{"name","profile_guid","seed"}], [...]],"score_raw","winner_side","scheduled_iso","court"}`. `round_index` 0 = final, ascending toward earlier rounds. Extends the existing `_DrawParser` (`bracket-round__title` for rounds; player/score capture per slot).

> **Plan note for the implementer:** The exact class names for player/score/winner inside a bracket slot must be confirmed against a REAL saved page (see Task 9's live-DOM confirmation, or save a real bracket page now). The fixture below encodes the *known* `bracket-round__title` structure plus plausible slot markup; if the real DOM differs, update BOTH the fixture and the parser together so the test still pins real behavior. Do NOT invent class names that you have not seen in a real page — capture one first.

- [ ] **Step 1: Create fixtures**

Save real saved HTML if available. If creating minimal fixtures, base them on the confirmed `bracket-round__title` structure:

```html
<!-- tests/fixtures/archive/draw_list.html -->
<html><body>
<a class="module__link" href="/sport/draw.aspx?id=AAAA&draw=10">Men's Doubles</a>
<a class="module__link" href="/sport/draw.aspx?id=AAAA&draw=11">Women's Singles</a>
</body></html>
```

```html
<!-- tests/fixtures/archive/bracket_elimination.html -->
<html><body>
<div class="bracket-round">
  <div class="bracket-round__title">Final</div>
  <div class="bracket-match">
    <div class="bracket-match__row bracket-match__row--winner">
      <span class="nav-link__value">Alice Smith</span>
    </div>
    <div class="bracket-match__row">
      <span class="nav-link__value">Bob Jones</span>
    </div>
    <div class="bracket-match__score">21-15 21-18</div>
  </div>
</div>
</body></html>
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_archive_parse.py
from pathlib import Path

from badminton_tracker import archive_parse

FIX = Path(__file__).parent / "fixtures" / "archive"


def test_parse_draw_list():
    html = (FIX / "draw_list.html").read_text(encoding="utf-8")
    draws = archive_parse.parse_draw_list(html)
    names = [d["name"] for d in draws]
    assert "Men's Doubles" in names and "Women's Singles" in names
    assert all(d["id"] for d in draws)


def test_parse_bracket_final_with_winner_and_score():
    html = (FIX / "bracket_elimination.html").read_text(encoding="utf-8")
    matches = archive_parse.parse_bracket(html)
    assert len(matches) == 1
    m = matches[0]
    assert m["round_label"] == "Final"
    assert m["round_index"] == 0
    assert m["score_raw"] == "21-15 21-18"
    assert m["winner_side"] == 1
    side_names = [[p["name"] for p in side] for side in m["sides"]]
    assert side_names == [["Alice Smith"], ["Bob Jones"]]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_archive_parse.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'badminton_tracker.archive_parse'`

- [ ] **Step 4: Write archive_parse.py**

```python
"""Pure HTML→dict parsers for tournament draw lists and full brackets.

No network. Unit-tested against saved fixtures. Extends the bracket-round
structure already parsed by upcoming_parse._DrawParser, but captures EVERY
match (not just the displayed group) with winner + score + per-slot players."""

from __future__ import annotations

import re
from html.parser import HTMLParser

_DRAW_LINK_RE = re.compile(
    r'<a[^>]*href="([^"]*draw[^"]*)"[^>]*>(.*?)</a>', re.I | re.S
)

# Round labels in finals-first order; round_index = position in this list when
# matched, else a large fallback so unknown rounds sort as "earliest".
_ROUND_ORDER = ["final", "semi", "quarter", "r16", "r32", "r64", "round of"]


def _round_index(label: str) -> int:
    low = label.lower()
    for i, key in enumerate(_ROUND_ORDER):
        if key in low:
            return i
    return 99


def parse_draw_list(html: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for i, m in enumerate(_DRAW_LINK_RE.finditer(html)):
        href = m.group(1)
        name = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if not name or href in seen:
            continue
        seen.add(href)
        out.append({"id": href, "name": name, "draw_type": "unknown", "ordering": i})
    return out


class _BracketParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.matches: list[dict] = []
        self._round_label: str | None = None
        self._position = 0
        self._cur: dict | None = None
        self._cur_side: list | None = None
        self._cur_winner = False
        self._capture: str | None = None  # 'round' | 'player' | 'score'
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if "bracket-round__title" in cls:
            self._capture, self._buf = "round", []
        elif "bracket-match" in cls and "bracket-match__" not in cls:
            self._cur = {"sides": [], "score_raw": None,
                         "scheduled_iso": None, "court": None,
                         "winner_side": None}
        elif "bracket-match__row" in cls and self._cur is not None:
            self._cur_side = []
            self._cur_winner = "--winner" in cls
        elif "nav-link__value" in cls and self._cur_side is not None:
            self._capture, self._buf = "player", []
        elif "bracket-match__score" in cls and self._cur is not None:
            self._capture, self._buf = "score", []
        elif tag == "time" and self._cur is not None:
            dt = a.get("datetime")
            if dt and self._cur["scheduled_iso"] is None:
                self._cur["scheduled_iso"] = dt

    def handle_data(self, data):
        if self._capture:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if self._capture == "round" and tag == "div":
            self._round_label = "".join(self._buf).strip()
            self._position = 0
            self._capture = None
        elif self._capture == "player":
            name = "".join(self._buf).strip()
            if name and self._cur_side is not None:
                self._cur_side.append(
                    {"name": name, "profile_guid": None, "seed": None})
            self._capture = None
        elif self._capture == "score":
            self._cur["score_raw"] = "".join(self._buf).strip() or None
            self._capture = None
        elif tag == "div" and self._cur_side is not None and self._capture is None:
            # closing a bracket-match__row: commit the side
            if self._cur_side:
                self._cur["sides"].append(self._cur_side)
                if self._cur_winner:
                    self._cur["winner_side"] = len(self._cur["sides"])
            self._cur_side = None
            self._cur_winner = False
        # NB: match commit handled in close of the match container below
        if tag == "div" and self._cur is not None and self._cur_side is None \
                and self._cur.get("sides") and self._capture is None:
            # Heuristic commit when a populated match container closes.
            if self._cur not in [m["_ref"] for m in self.matches if "_ref" in m]:
                pass

    def commit_open_match(self):
        if self._cur and self._cur["sides"]:
            self._cur["round_label"] = self._round_label or ""
            self._cur["round_index"] = _round_index(self._round_label or "")
            self._cur["position"] = self._position
            self._position += 1
            self.matches.append(self._cur)
        self._cur = None


def parse_bracket(html: str) -> list[dict]:
    p = _BracketParser()
    # Commit each match when the next match starts or at end. Simplest robust
    # approach: split on the match container, parse each chunk independently.
    chunks = re.split(r'(?=<div class="[^"]*bracket-match(?:")[^"]*")', html)
    out: list[dict] = []
    round_label = None
    rl = re.findall(r'bracket-round__title[^>]*>(.*?)<', html, re.I | re.S)
    # Fall back to per-chunk parsing with a fresh parser that commits at end.
    for chunk in chunks:
        sp = _BracketParser()
        sp.feed(chunk)
        sp.commit_open_match()
        out.extend(sp.matches)
    return out
```

> **Plan note:** The `_BracketParser` commit logic is the trickiest part and depends on real DOM nesting. The implementer MUST validate against a real saved bracket page and simplify the commit strategy (the chunk-split in `parse_bracket` is a robust fallback that parses one match container at a time). If the real DOM gives a cleaner per-match container, prefer a single-pass parser that calls `commit_open_match()` when a new `bracket-match` container opens. Keep the test green against the real fixture.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_archive_parse.py -v`
Expected: PASS (2 tests). If the commit heuristic mis-parses the minimal fixture, simplify per the plan note until both tests pass against a real saved page.

- [ ] **Step 6: ruff + commit**

```bash
uv run ruff check src/badminton_tracker/archive_parse.py
git add src/badminton_tracker/archive_parse.py tests/test_archive_parse.py tests/fixtures/archive/draw_list.html tests/fixtures/archive/bracket_elimination.html
git commit -m "feat(archive): draw-list + bracket parsers"
```

---

### Task 6: Fetch + raw-cache (with fake-client tests)

**Files:**
- Create: `src/badminton_tracker/archive_fetch.py`
- Test: `tests/test_archive_crawl.py` (fetch portion)

**Interfaces:**
- Consumes: `archive_db` (raw_cache table), `config.ARCHIVE_RAW_DIR`.
- Produces:
  - `cache_get(conn, url: str) -> str | None` — return cached body text if present (reads `body_path`), else None.
  - `cache_put(conn, url: str, body: str, status_code: int, now: str) -> str` — write body to a content-addressed file under `ARCHIVE_RAW_DIR`, record in `raw_cache`, return the file path.
  - `fetch(conn, url: str, getter, now: str, *, delay_ms: int = 700) -> str` — return cached body if present; else call `getter(url) -> (body, status)`, cache it, return body. `getter` is injected so tests use a fake (no Playwright/network).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_archive_crawl.py
from badminton_tracker import archive_db, archive_fetch


def test_fetch_caches_and_does_not_refetch(tmp_path, monkeypatch):
    from badminton_tracker import config
    monkeypatch.setattr(config, "ARCHIVE_RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(archive_fetch, "ARCHIVE_RAW_DIR", tmp_path / "raw",
                        raising=False)
    conn = archive_db.connect(tmp_path / "a.sqlite")
    calls = []

    def getter(url):
        calls.append(url)
        return ("<html>hi</html>", 200)

    b1 = archive_fetch.fetch(conn, "http://x/1", getter, now="t", delay_ms=0)
    b2 = archive_fetch.fetch(conn, "http://x/1", getter, now="t", delay_ms=0)
    assert b1 == b2 == "<html>hi</html>"
    assert calls == ["http://x/1"]  # second call served from cache
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_archive_crawl.py::test_fetch_caches_and_does_not_refetch -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'badminton_tracker.archive_fetch'`

- [ ] **Step 3: Write archive_fetch.py**

```python
"""Fetch + content-addressed raw cache. The HTTP getter is injected so the
cache logic is testable without network; the live driver supplies a Playwright
getter. Politeness (delay) lives here too."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from .config import ARCHIVE_RAW_DIR


def _hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def cache_get(conn, url: str) -> str | None:
    row = conn.execute(
        "SELECT body_path FROM raw_cache WHERE url_hash=?", (_hash(url),)
    ).fetchone()
    if row is None:
        return None
    p = Path(row["body_path"])
    return p.read_text(encoding="utf-8") if p.exists() else None


def cache_put(conn, url: str, body: str, status_code: int, now: str) -> str:
    raw_dir = Path(ARCHIVE_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    h = _hash(url)
    body_path = raw_dir / f"{h}.html"
    body_path.write_text(body, encoding="utf-8")
    conn.execute(
        """INSERT INTO raw_cache (url_hash,url,body_path,status_code,fetched_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(url_hash) DO UPDATE SET
             body_path=excluded.body_path, status_code=excluded.status_code,
             fetched_at=excluded.fetched_at""",
        (h, url, str(body_path), status_code, now),
    )
    conn.commit()
    return str(body_path)


def fetch(conn, url: str, getter, now: str, *, delay_ms: int = 700) -> str:
    cached = cache_get(conn, url)
    if cached is not None:
        return cached
    if delay_ms:
        time.sleep(delay_ms / 1000.0)
    body, status = getter(url)
    cache_put(conn, url, body, status, now)
    return body
```

> **Implementer note:** the test monkeypatches `ARCHIVE_RAW_DIR`. Because it's imported by value, the test sets it on the module (`archive_fetch.ARCHIVE_RAW_DIR`); `cache_put` reads the module global, so reference it as a module attribute or re-read from config. Simplest: in `cache_put`/`fetch`, use `from . import config` and `config.ARCHIVE_RAW_DIR`. Adjust the import style so the monkeypatch on `config.ARCHIVE_RAW_DIR` is honored, and update the test to patch only `config.ARCHIVE_RAW_DIR`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_archive_crawl.py::test_fetch_caches_and_does_not_refetch -v`
Expected: PASS

- [ ] **Step 5: ruff + commit**

```bash
uv run ruff check src/badminton_tracker/archive_fetch.py
git add src/badminton_tracker/archive_fetch.py tests/test_archive_crawl.py
git commit -m "feat(archive): fetch + content-addressed raw cache"
```

---

### Task 7: Crawl state-machine run loop (resume + idempotency)

**Files:**
- Create: `src/badminton_tracker/archive_crawl.py`
- Test: `tests/test_archive_crawl.py` (append)

**Interfaces:**
- Consumes: `archive_db`, `archive_fetch`, `archive_enumerate`, `archive_parse`.
- Produces:
  - `process_tournament(conn, tid: str, fetch_fn, now: str) -> None` — runs fetch→parse→store for one tournament, setting `crawl_state` to `done` on success or `error` on exception. `fetch_fn(url) -> str` is injected.
  - `run(conn, tournament_ids: list[dict], fetch_fn, now: str) -> dict` — upserts tournaments + `pending` state, processes every non-`done` tournament, returns `{"done": n, "error": m}`. Idempotent: re-running skips `done`.

> **Implementer note:** keep `process_tournament`'s URL construction (draws page, per-draw bracket page) in ONE place; confirm the real URL templates in Task 9. For the test, `fetch_fn` returns fixture HTML keyed by URL substring, so no network and no real templates are needed to prove the state machine.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_archive_crawl.py  (append)
from badminton_tracker import archive_crawl


def _fake_fetch(url):
    if "draws" in url:
        return ('<a class="module__link" href="/sport/draw.aspx?id=D&draw=1">MD</a>')
    return ('<div class="bracket-round"><div class="bracket-round__title">Final'
            '</div><div class="bracket-match">'
            '<div class="bracket-match__row bracket-match__row--winner">'
            '<span class="nav-link__value">Alice</span></div>'
            '<div class="bracket-match__row">'
            '<span class="nav-link__value">Bob</span></div>'
            '<div class="bracket-match__score">21-10 21-12</div></div></div>')


def test_run_is_idempotent_and_resumable(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")
    tlist = [{"id": "T1", "name": "Cup 2024", "start_date": "2024-04-12"}]
    r1 = archive_crawl.run(conn, tlist, _fake_fetch, now="t")
    assert r1["done"] == 1 and r1["error"] == 0
    n_matches_1 = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    # Re-run: T1 already done → skipped, no duplicate matches.
    r2 = archive_crawl.run(conn, tlist, _fake_fetch, now="t")
    assert r2["done"] == 0  # nothing re-processed
    n_matches_2 = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    assert n_matches_1 == n_matches_2
    conn.close()


def test_run_records_error_without_crashing(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")

    def boom(url):
        raise RuntimeError("network down")

    r = archive_crawl.run(conn, [{"id": "T9", "name": "X", "start_date": None}],
                          boom, now="t")
    assert r["error"] == 1
    row = conn.execute(
        "SELECT status, last_error FROM crawl_state WHERE tournament_id='T9'"
    ).fetchone()
    assert row["status"] == "error" and "network down" in row["last_error"]
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_archive_crawl.py::test_run_is_idempotent_and_resumable -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'badminton_tracker.archive_crawl'`

- [ ] **Step 3: Write archive_crawl.py**

```python
"""Resumable crawl state machine. Ties enumerate→fetch→parse→store together,
checkpointing each tournament in crawl_state so an interrupted multi-day run
resumes cleanly. The fetch function is injected (Playwright live, fake in tests)."""

from __future__ import annotations

import re

from . import archive_db, archive_parse
from .config import BASE_URL


def _year_of(start_date: str | None) -> int | None:
    return int(start_date[:4]) if start_date else None


def _draws_url(tid: str) -> str:
    return f"{BASE_URL}/sport/draws.aspx?id={tid}"


def _bracket_url(draw_href: str) -> str:
    if draw_href.startswith("http"):
        return draw_href
    return f"{BASE_URL}{draw_href}" if draw_href.startswith("/") else \
        f"{BASE_URL}/{draw_href}"


def process_tournament(conn, tid: str, fetch_fn, now: str) -> None:
    draws_html = fetch_fn(_draws_url(tid))
    draws = archive_parse.parse_draw_list(draws_html)
    for d in draws:
        draw_id = d["id"]
        archive_db.upsert_draw(conn, {
            "id": draw_id, "tournament_id": tid, "name": d["name"],
            "draw_type": d["draw_type"], "ordering": d["ordering"]})
        bracket_html = fetch_fn(_bracket_url(d["id"]))
        for m in archive_parse.parse_bracket(bracket_html):
            side_ids = []
            for side in m["sides"]:
                ids = []
                for pl in side:
                    pid = archive_db.upsert_player(conn, {
                        "tournament_id": tid, "display_name": pl["name"],
                        "profile_guid": pl.get("profile_guid"),
                        "club": None, "seed": pl.get("seed")})
                    ids.append(pid)
                side_ids.append(ids)
            archive_db.insert_match(conn, {
                "draw_id": draw_id, "round_label": m["round_label"],
                "round_index": m["round_index"], "position": m["position"],
                "side1_player_ids": side_ids[0] if len(side_ids) > 0 else [],
                "side2_player_ids": side_ids[1] if len(side_ids) > 1 else [],
                "score_raw": m["score_raw"], "winner_side": m["winner_side"],
                "scheduled_iso": m["scheduled_iso"], "court": m["court"]})


def run(conn, tournament_ids: list[dict], fetch_fn, now: str) -> dict:
    for t in tournament_ids:
        archive_db.upsert_tournament(conn, {
            "id": t["id"], "name": t.get("name"),
            "year": _year_of(t.get("start_date")),
            "start_date": t.get("start_date"), "end_date": t.get("start_date"),
            "location": None, "region": None, "category": None,
            "source_url": f"{BASE_URL}/sport/tournament?id={t['id']}",
            "fetched_at": now})
        existing = conn.execute(
            "SELECT status FROM crawl_state WHERE tournament_id=?", (t["id"],)
        ).fetchone()
        if existing is None:
            archive_db.set_state(conn, t["id"], "pending", now=now)

    done = err = 0
    for tid in archive_db.pending_tournaments(conn):
        try:
            process_tournament(conn, tid, fetch_fn, now)
            archive_db.set_state(conn, tid, "done", now=now)
            done += 1
        except Exception as e:  # noqa: BLE001 — record + continue, never crash the crawl
            archive_db.set_state(conn, tid, "error", error=str(e), now=now)
            err += 1
    return {"done": done, "error": err}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_archive_crawl.py -v`
Expected: PASS (all)

- [ ] **Step 5: ruff + commit**

```bash
uv run ruff check src/badminton_tracker/archive_crawl.py
git add src/badminton_tracker/archive_crawl.py tests/test_archive_crawl.py
git commit -m "feat(archive): resumable crawl state machine"
```

---

### Task 8: Privacy-guard test

**Files:**
- Create: `tests/test_archive_privacy.py`

**Interfaces:**
- Consumes: `config`.

- [ ] **Step 1: Write the test (this one is allowed to pass immediately — it pins invariants)**

```python
# tests/test_archive_privacy.py
import json
from pathlib import Path

from badminton_tracker import config


def test_archive_store_is_under_private_data_dir_only():
    assert config.DATA_DIR in config.ARCHIVE_DB.parents
    assert config.DATA_DIR in config.ARCHIVE_RAW_DIR.parents
    web = (Path(config.__file__).resolve().parents[2] / "web")
    # Archive must NOT live under web/ (the publishable dir).
    assert web not in config.ARCHIVE_DB.parents
    assert web not in config.ARCHIVE_RAW_DIR.parents


def test_public_jsons_contain_no_profile_guids():
    root = Path(config.__file__).resolve().parents[2]
    guid = __import__("re").compile(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
    data = root / "web" / "data.json"
    if data.exists():
        # data.json must contain ZERO GUIDs (no tournament guids belong here).
        assert not guid.search(data.read_text(encoding="utf-8"))
    # upcoming.json MAY contain the tournament guid but is checked elsewhere;
    # here we only assert data.json stays GUID-free.


def test_no_archive_import_in_public_pipeline():
    src = Path(config.__file__).resolve().parent
    for mod in ("build.py", "export.py"):
        text = (src / mod).read_text(encoding="utf-8")
        assert "archive_db" not in text
        assert "archive_crawl" not in text
        assert "archive_fetch" not in text
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_archive_privacy.py -v`
Expected: PASS (3 tests). If `test_public_jsons_contain_no_profile_guids` fails, the public snapshot already leaks a GUID — STOP and report; do not weaken the test.

- [ ] **Step 3: Commit**

```bash
git add tests/test_archive_privacy.py
git commit -m "test(archive): privacy-guard invariants"
```

---

### Task 9: Live driver + CLI wiring (`archive-crawl`)

**Files:**
- Modify: `src/badminton_tracker/archive_crawl.py` (add live `main`)
- Modify: `src/badminton_tracker/__main__.py` (add subcommand)

**Interfaces:**
- Consumes: `client.ensure_login`, `client.new_context`, `client.dismiss_cookies`, `archive_enumerate`.
- Produces:
  - `crawl_live(*, year_from: int, year_to: int, refresh_months: int | None, delay_ms: int, max_pages: int) -> dict` — logs in via Playwright, enumerates tournaments across the year range (paginating `/find/tournament`), builds a Playwright `fetch_fn` wrapping `archive_fetch.fetch`, and calls `run(...)`. Returns the `run` summary.

> **Implementer — REQUIRED live-DOM confirmation step before coding `crawl_live`:** With creds in `.env`, save ONE real tournament's draws page and ONE real bracket page to `tests/fixtures/archive/` (use the existing scrape entry as reference — see memory note [[scraper-creds-env-shadowing]]: empty `TOURNAMENTSOFTWARE_*` shell vars shadow `.env`; `unset` them in the same command). Confirm the real URL templates for the draws list and bracket pages and the real slot/winner/score class names. Update `_draws_url`, `_bracket_url`, and the parser + fixtures to match REAL DOM, keeping all tests green. Do NOT ship guessed URLs/classes.

- [ ] **Step 1: Add `crawl_live` to archive_crawl.py**

```python
def crawl_live(*, year_from: int, year_to: int, refresh_months=None,
               delay_ms: int = 700, max_pages: int = 40) -> dict:  # pragma: no cover
    """Live driver: login → enumerate year range → fetch+cache+parse+store."""
    from datetime import datetime, timezone

    from playwright.sync_api import sync_playwright

    from . import archive_enumerate, archive_fetch, client

    now = datetime.now(timezone.utc).isoformat()
    conn = archive_db.connect()
    with sync_playwright() as p:
        browser, ctx = client.new_context(p, headless=True)
        try:
            page = client.ensure_login(ctx)

            def getter(url):
                page.goto(url, wait_until="domcontentloaded")
                client.dismiss_cookies(page)
                page.wait_for_timeout(300)
                return (page.content(), 200)

            def fetch_fn(url):
                return archive_fetch.fetch(conn, url, getter, now, delay_ms=delay_ms)

            tournaments: dict[str, dict] = {}
            for year in range(year_from, year_to + 1):
                for pg in range(1, max_pages + 1):
                    url = (f"{BASE_URL}/find/tournament?TournamentFilter."
                           f"DateFilterType=0&YearNr={year}&page={pg}")
                    html = fetch_fn(url)
                    found = archive_enumerate.parse_tournament_list(html)
                    if not found:
                        break
                    before = len(tournaments)
                    for t in found:
                        tournaments.setdefault(t["id"].lower(), t)
                    if len(tournaments) == before:
                        break
            return run(conn, list(tournaments.values()), fetch_fn, now)
        finally:
            ctx.close()
            browser.close()
            conn.close()
```

- [ ] **Step 2: Add the subcommand to __main__.py**

In the parser-building section (near the other `sub.add_parser(...)` calls):

```python
    p_arch = sub.add_parser(
        "archive-crawl",
        help="PRIVATE: crawl all tournaments (year range) into the SQLite archive")
    p_arch.add_argument("--year-from", type=int, default=2020)
    p_arch.add_argument("--year-to", type=int, default=2026)
    p_arch.add_argument("--refresh-months", type=int, default=None,
                        help="light top-up mode (seed of sub-project C)")
    p_arch.add_argument("--delay-ms", type=int, default=700)
```

In the dispatch section (where commands are handled):

```python
    if args.command == "archive-crawl":
        from .archive_crawl import crawl_live
        summary = crawl_live(
            year_from=args.year_from, year_to=args.year_to,
            refresh_months=args.refresh_months, delay_ms=args.delay_ms)
        print(f"archive-crawl: {summary}")
        return
```

> **Implementer note:** match the EXACT dispatch style already in `__main__.py` (it uses `args.command == "..."` blocks or a handler map — follow whichever is present; read the file first).

- [ ] **Step 3: Verify CLI parses (no network)**

Run: `uv run badminton archive-crawl --help`
Expected: help text listing `--year-from`, `--year-to`, `--refresh-months`, `--delay-ms`.

- [ ] **Step 4: Full test suite + ruff**

Run: `uv run pytest -q && uv run ruff check`
Expected: all green, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/badminton_tracker/archive_crawl.py src/badminton_tracker/__main__.py
git commit -m "feat(archive): live Playwright driver + archive-crawl CLI"
```

---

### Task 10: Authed read endpoints (`/api/archive/*`)

**Files:**
- Modify: `src/badminton_tracker/server.py`
- Test: `tests/test_archive_endpoints.py`

**Interfaces:**
- Consumes: `archive_db`, existing `_check_password` / `EDIT_PASSWORD` pattern in `server.py`.
- Produces:
  - `GET /api/archive/tournaments?password=...` → `[{"id","name","year","start_date"}]`.
  - `GET /api/archive/tournament/{tid}/bracket?password=...` → `{"tournament": {...}, "draws": [{"id","name","matches": [...] }]}`.
  - Both require the edit password (same posture as the Maintain tab). No password / wrong password → 401/403. Archive DB missing → empty lists (not a crash).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_archive_endpoints.py
import importlib

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch, password="secret"):
    from badminton_tracker import config
    monkeypatch.setattr(config, "EDIT_PASSWORD", password)
    monkeypatch.setattr(config, "ARCHIVE_DB", tmp_path / "a.sqlite")
    from badminton_tracker import archive_db, server
    importlib.reload(server)  # pick up patched EDIT_PASSWORD in module-level refs
    conn = archive_db.connect(tmp_path / "a.sqlite")
    archive_db.upsert_tournament(conn, {
        "id": "T1", "name": "Cup 2024", "year": 2024, "start_date": "2024-04-12",
        "end_date": "2024-04-12", "location": None, "region": None,
        "category": None, "source_url": None, "fetched_at": "t"})
    conn.close()
    return TestClient(server.app)


def test_tournaments_requires_password(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.get("/api/archive/tournaments").status_code in (401, 403)


def test_tournaments_lists_with_password(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.get("/api/archive/tournaments", params={"password": "secret"})
    assert r.status_code == 200
    assert any(t["id"] == "T1" for t in r.json())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_archive_endpoints.py -v`
Expected: FAIL (404 — routes not defined yet — so the assertions don't match).

- [ ] **Step 3: Add endpoints to server.py**

Add near the other routes (use the established `_check_password` helper and `ARCHIVE_DB` from config):

```python
from .config import ARCHIVE_DB  # add to the existing config import line


@app.get("/api/archive/tournaments")
def archive_tournaments(password: str | None = None):
    _check_password(password)
    from . import archive_db
    if not ARCHIVE_DB.exists():
        return []
    conn = archive_db.connect(ARCHIVE_DB)
    try:
        rows = conn.execute(
            "SELECT id,name,year,start_date FROM tournaments ORDER BY year DESC, name"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/archive/tournament/{tid}/bracket")
def archive_bracket(tid: str, password: str | None = None):
    _check_password(password)
    from . import archive_db
    if not ARCHIVE_DB.exists():
        raise HTTPException(404, "Archive not built")
    conn = archive_db.connect(ARCHIVE_DB)
    try:
        t = conn.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
        if t is None:
            raise HTTPException(404, "Unknown tournament")
        draws = []
        for d in conn.execute(
            "SELECT * FROM draws WHERE tournament_id=? ORDER BY ordering", (tid,)
        ).fetchall():
            matches = [dict(m) for m in conn.execute(
                "SELECT * FROM matches WHERE draw_id=? ORDER BY round_index, position",
                (d["id"],)).fetchall()]
            draws.append({**dict(d), "matches": matches})
        return {"tournament": dict(t), "draws": draws}
    finally:
        conn.close()
```

> **Implementer note:** `_check_password` raises `HTTPException(403)` when no edit password is set and `401` on a wrong one — exactly the Maintain-tab posture. Confirm `HTTPException` is already imported in `server.py` (it is, per the existing `_check_password`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_archive_endpoints.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Full suite + ruff + commit**

```bash
uv run pytest -q && uv run ruff check
git add src/badminton_tracker/server.py tests/test_archive_endpoints.py
git commit -m "feat(archive): authed /api/archive read endpoints"
```

---

### Task 11: gitignore guard + README note

**Files:**
- Modify: `data/.gitignore` (private repo) OR confirm the public repo already ignores `data/`
- Modify: `README.md` (brief private-archive note)

**Interfaces:** none.

- [ ] **Step 1: Confirm the archive dir is ignored by the PUBLIC repo**

Run: `git -C g:/proj/badminton_bros check-ignore data/archive/archive.sqlite`
Expected: prints the path (it is ignored, because the public repo ignores all of `data/`). If it prints nothing, STOP — add `data/` to the public `.gitignore` before going further.

- [ ] **Step 2: Add a private-archive note to README.md**

Add a short subsection under the workflow docs:

```markdown
### Private historical archive (backend-only)

`uv run badminton archive-crawl --year-from 2020 --year-to 2026` builds a
PRIVATE SQLite archive of every Finnish-badminton tournament in the range
(`data/archive/archive.sqlite` + raw cache under `data/archive/raw/`). It is
never published: browse it only via the authed endpoints `/api/archive/...`
(same edit password as the Maintain tab) while the server is running. The
public `web/data.json` / `web/upcoming.json` are unaffected.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(archive): note the backend-only private archive"
```

---

## Self-Review

**Spec coverage:** enumerate (T4), fetch+raw-cache (T6), parse full bracket (T5), normalized SQLite (T2/T3), resumable state machine (T7), backend-only authed access (T10), privacy guard (T8), config/private store (T1/T11), CLI `--full`/`--refresh` modes (T9). All spec sections map to tasks.

**Placeholder scan:** Every code step shows real code. Two tasks (T5 bracket parser, T9 live driver) carry explicit **implementer notes requiring live-DOM confirmation** — these are not placeholders but mandatory verification steps, because the exact slot/winner class names and URL templates can only be pinned against a real saved page (consistent with the spec's "confirm against live DOM" risk).

**Type consistency:** `parse_bracket` returns `sides` (list of sides, each a list of `{name,profile_guid,seed}`); `process_tournament` consumes `m["sides"]` and `pl["name"]`/`pl.get("profile_guid")`/`pl.get("seed")` — consistent. `upsert_player` returns `int`; `process_tournament` collects those ints into `side_ids` → stored via `insert_match` as JSON lists — consistent with T3's `insert_match`. `set_state`/`pending_tournaments` signatures match T3 and T7 usage. `crawl_live`/`run`/`process_tournament` signatures consistent across T7/T9.

**Known soft spot (flagged for the executor):** the `_BracketParser` commit heuristic in T5 is the riskiest code and explicitly depends on real DOM nesting. The plan provides a robust chunk-split fallback and instructs the implementer to simplify against a real fixture. This is the one place to expect iteration.

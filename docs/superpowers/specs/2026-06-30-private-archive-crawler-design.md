# Private Archive Crawler + SQLite Store — Design

**Date:** 2026-06-30
**Status:** SPEC — approved-pending-review
**Sub-project:** A (of A→B→C→D decomposition below)

## Why

The project today scrapes the **friend group** specifically and publishes a small,
GUID-free public snapshot. The user wants, additionally, a **complete private
archive** of Finnish badminton (`badmintonfinland.tournamentsoftware.com`) from
**2020→now** — every tournament, every draw, every match, every player — with the
**full bracket structure preserved**, so that:

- tournament **brackets can be visualized** (the user's primary motivation), and
- a future **strict, human-confirmed name-matching** layer has a clean foundation.

This is explicitly a **private, backend-only** archive. It does NOT touch the
public site, and it upholds CLAUDE.md rule #4 (privacy is the architecture): the
only publishable artifact remains the GUID-free `web/*.json`.

## Decomposition (this spec is sub-project A)

| # | Sub-project | Depends on | Status |
|---|---|---|---|
| **A** | **Private archive crawler + SQLite store** (this spec) | — | spec'd here |
| **B** | **Tournament bracket visualization** (the payoff) | A | future spec |
| **C** | **Auto-keep-current** (scheduled monthly light refresh) | A | thin wrapper, future |
| **D** | **Strict name-matching / identity overview** | A | already spec'd: `2026-06-28-multi-nickname-identity-and-name-discovery-design.md` |

Each of B/C/D gets its own spec → plan → build cycle. **A defers ALL
cross-tournament person-merging to D** — A only faithfully captures what the site
shows. That separation is the strictness: capture is dumb and exact; matching is a
separate, auditable, human-confirmed step.

## Scope

- **In:** site-wide enumeration 2020→now; fetch + raw-cache; parse full bracket
  structure; normalized SQLite store; resumable crawl-state machine; backend-only
  authed read endpoints; privacy-guard test.
- **Out (deferred):** cross-tournament identity merging (D); bracket viz UI (B);
  scheduled/daemon refresh (C, though the `--refresh` entry seed is built here);
  any change to the public build/export/site.

## Architecture — four isolated layers

```
enumerate ──▶ fetch + raw-cache ──▶ parse (pure) ──▶ store (SQLite)
   │                                                      ▲
   └────────────── crawl_state checkpoints ───────────────┘
```

1. **Enumerate** — list every tournament 2020→now. Generalize the existing
   `upcoming_find.py` `/find/tournament?YearNr=` approach into a year-range
   enumerator. Output: rows in `tournaments` + `crawl_state(pending)`.
2. **Fetch + raw-cache** — per tournament: draw list, each draw's full bracket
   HTML, matches. **Every HTTP response is written to a content-addressed raw
   cache on disk before parsing.** Re-parsing never re-downloads. Throttled,
   concurrency 1, resumable. Reuses authenticated `client.py` (cookie persistence
   already solved).
3. **Parse** — pure `HTML → dict` functions extending the proven `_DrawParser`
   (`upcoming_parse.py`). Extract rounds, slots, seeds, players, scores, winner
   edges, schedule/court. **No network** — unit-tested against saved fixtures.
4. **Store** — normalized SQLite + `crawl_state` for resumability.

## SQLite schema (private store)

```
tournaments
  id            TEXT PRIMARY KEY     -- tournament's own public GUID (allowed; public event id)
  name          TEXT
  year          INTEGER
  start_date    TEXT                 -- ISO
  end_date      TEXT
  location      TEXT
  region        TEXT                 -- nullable
  category      TEXT                 -- nullable (level/grade)
  source_url    TEXT
  fetched_at    TEXT

draws
  id            TEXT PRIMARY KEY     -- draw GUID/slug
  tournament_id TEXT REFERENCES tournaments(id)
  name          TEXT                 -- "Men's Doubles", "MD A", ...
  draw_type     TEXT                 -- elimination | round-robin | unknown
  ordering      INTEGER

players                              -- PER-TOURNAMENT identity, NOT cross-tournament merged
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  tournament_id TEXT REFERENCES tournaments(id)
  display_name  TEXT                 -- exactly as the site shows
  profile_guid  TEXT                 -- nullable; PRIVATE only, NEVER published
  club          TEXT
  seed          INTEGER              -- nullable
  UNIQUE(tournament_id, display_name, profile_guid)

matches
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  draw_id           TEXT REFERENCES draws(id)
  round_label       TEXT             -- "Final", "R16", "Group A", ...
  round_index       INTEGER          -- 0 = final, ascending toward earlier rounds
  position          INTEGER          -- slot within round (bracket y-order)
  side1_player_ids  TEXT             -- JSON array of players.id (1 = singles, 2 = doubles)
  side2_player_ids  TEXT
  score_raw         TEXT             -- "21-15 19-21 21-18"
  winner_side       INTEGER          -- 1 | 2 | NULL (walkover/unplayed)
  scheduled_iso     TEXT
  court             TEXT

crawl_state
  tournament_id TEXT PRIMARY KEY REFERENCES tournaments(id)
  status        TEXT                 -- pending | fetched | parsed | done | error
  attempts      INTEGER DEFAULT 0
  last_error    TEXT
  updated_at    TEXT

raw_cache                            -- content-addressed; re-parse never re-downloads
  url_hash      TEXT PRIMARY KEY     -- sha256 of URL
  url           TEXT
  body_path     TEXT                 -- file on disk under private raw-cache dir
  status_code   INTEGER
  fetched_at    TEXT
```

**Strictness choices:**
- `players` is **per-tournament** (no merging in A; D merges via review queue).
- `round_index` + `position` are stored explicitly so bracket viz (B) lays out the
  tree without re-deriving topology.

## Crawl-state machine (resumable, polite)

```
pending  ──fetch all pages (→ raw_cache)──▶ fetched
fetched  ──parse HTML → upsert rows───────▶ parsed
parsed   ──integrity check passes─────────▶ done
  any step throws ─────────────────────────▶ error (attempts++, last_error)
```

- **Run loop:** enumerate 2020→now → upsert `tournaments` + `crawl_state(pending)`
  → process every non-`done` row.
- **Resume is the default.** Re-running skips `done`, retries `error` (up to N
  attempts), continues `pending`/`fetched`.
- **Politeness:** concurrency 1, configurable inter-request delay, exponential
  backoff on errors.
- **Idempotent:** upserts keyed on GUIDs / UNIQUE constraints — re-parsing the same
  cache never duplicates rows.
- **One verb, two modes:**
  - `badminton archive-crawl --full` — 2020→now (first run).
  - `badminton archive-crawl --refresh --since-months N` — light top-up
    (seed of sub-project C).

## Backend-only access

The archive is **never** read by the public build/export path. It is exposed only
through the already-running FastAPI server (`server.py`), behind the **edit
password** that already gates the Maintain tab:

- New PRIVATE endpoints, e.g.
  - `GET /api/archive/tournaments`
  - `GET /api/archive/tournament/{id}/bracket`
  all require the same `BADMINTON_EDIT_PASSWORD` auth maintain already uses.
- Server off → no access. `BADMINTON_EDIT_PASSWORD` unset → archive endpoints
  disabled (same posture as editing).

## Privacy guard (hard requirement)

A test asserts:
- archive DB + raw cache live **only** under the private store (not the public repo,
  not `web/`),
- `web/data.json` / `web/upcoming.json` never gain archive-sourced data or any
  **profile** GUID,
- the public build/export pipeline does not read the archive at all.

The public site must stay **byte-for-byte unaffected** by this sub-project.

## Storage location

- Archive DB: private store (e.g. `data/archive/archive.sqlite`) — inside the
  private nested repo, gitignored by the public repo like the rest of `data/`.
- Raw cache: `data/archive/raw/` (content-addressed files).
- (Exact path finalized in the implementation plan; constraint is: private-only.)

## New modules (proposed, isolated)

- `archive_db.py` — schema creation, connection, upsert helpers.
- `archive_enumerate.py` — year-range tournament enumeration.
- `archive_fetch.py` — fetch + raw-cache (uses `client.py`), throttle/backoff.
- `archive_parse.py` — pure HTML→dict bracket parsers (extends `_DrawParser`).
- `archive_crawl.py` — the state-machine run loop + CLI wiring.
- archive read endpoints added to `server.py` (authed).

Each: clear single purpose, well-defined dict interfaces, independently testable.

## Testing

- **Parse:** unit tests over saved HTML fixtures (elimination + round-robin draws,
  singles + doubles, walkovers, byes, in-progress/unplayed).
- **State machine:** resume/idempotency tests (interrupt mid-crawl → re-run →
  no dupes, `done` skipped, `error` retried).
- **Privacy guard:** the assertions above.
- **Politeness:** delay/backoff exercised via a fake client (no real network in
  tests).

## Risks / open questions (resolve in plan)

- **Scale.** Whole site 2020→now may be thousands of tournaments. Mitigation:
  resumable + raw-cache + run over days; `--full` is expected to be long.
- **DOM variance.** Older (2020-era) tournament pages may differ from current DOM.
  Mitigation: fixtures from multiple years; parser tolerant of missing fields.
- **Auth/rate limits.** Reuse cookie persistence; backoff; concurrency 1.
- **Exact draw/match URL patterns** for full brackets (vs. the upcoming pipeline's
  partial view) — confirm against live DOM during Task 1 of the plan.

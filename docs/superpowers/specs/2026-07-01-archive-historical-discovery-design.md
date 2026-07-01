# Archive historical discovery — design

**Date:** 2026-07-01
**Status:** Design (approved for planning)
**Sub-project:** A (private archive) — the historical-discovery follow-up that fills
the currently-EMPTY archive DB.

## Problem

Sub-project A shipped a private SQLite archive + resumable crawl state machine +
authed `/api/archive/*` endpoints (commit `973a1ee`), **but the archive is empty.**
The wired-up `crawl_live` enumerates `/find/tournament?YearNr=…`, which the live site
**ignores** — it only ever returns the ~14 current *upcoming* tournaments. There is no
path from that enumeration to finished 2020–2025 history, so the crawl reaches nothing
and stores nothing.

Two blockers had to be resolved before any build:
1. **Discovery** — where do finished-tournament GUIDs come from?
2. **Extraction** — how does a finished tournament's real match/bracket DOM
   materialize? (A prior probe found `draw.aspx` returned JS-empty markup and the
   committed parser keys on classes that never appear live.)

## Go/No-Go probe (2026-07-01) — both blockers resolved

A throwaway live probe (host, `.env` creds) against real profile GUIDs Tong
(`b6495bee…`) and Chau (`d69f71b9…`) established, with captured DOM as evidence:

- **Discovery WORKS.** `/player-profile/{guid}` is **server-rendered** and lists a
  player's finished tournaments as `/sport/tournament?id=GUID` +
  `/sport/draw.aspx?id=GUID&draw=N` links, reaching back years (Tong: 2025 & 2021).
  This is the historical-GUID source the prior session lacked. `/find/tournament`
  year-enum stays dead and is abandoned.
- **Extraction WORKS.** Two sources materialize real match DOM. We choose
  **`/sport/matches.aspx?id=GUID`**: **server-rendered, all draws in one fetch**
  (927 match rows observed), politer than N per-draw JS-rendered `draw.aspx` fetches.

### Real DOM contract (the committed parser is WRONG — `bracket-round__title` = 0 live)

On `matches.aspx`, **every match self-describes its draw and round**:

- Match item: `li.match-group__item > div.match.match--list`.
  (The `h5.match-group__header` sticky groups by *time* — ignore it.)
- Draw + round header: `ul.match__header-title` →
  - item 1: `<a href="/sport/draw.aspx?id=GUID&draw=N">` with `.nav-link__value` =
    **draw name** (e.g. "WS V") → gives `draw_id` (`GUID:N`) and `draw_name`.
  - item 2: `<span title="Semi final">` → **round label**.
- Player row: `div.match__row` (winner = `match__row has-won`).
- Name: `a.nav-link .nav-link__value` → "Noora Nokkala [1]" (trailing `[n]` = seed).
- Profile GUID + player-no: the row's `<a href="/sport/player.aspx?id={guid}&player=N">`.
- Score: `div.match__result > ul.points > li.points__cell` (winning set =
  `points__cell--won`); one `<ul.points>` per game. Empty `match__result` = walkover.
- Time: `div.match__footer .nav-link__value` → "la 9.5.2026 18.00".

Evidence lives in the session scratchpad only (raw captures hold real GUIDs + names).

## Scope (v1)

- **Seed:** the **9 core friends** in `data/players.csv` that have a `profile_guid`
  (Tong, Maila, Junya, Tanisha, Toni, Dhirav, Santeri, Chau, Hien Köhler).
  **Confirm at plan time:** [[no-pre-2026-history]] excluded "Toni" as a wrong
  identity — verify whether this GUID is the real friend before seeding it.
- **Source:** `matches.aspx` (bulk) only. `draw.aspx` per-draw geometry deferred.
- **Union** the discovered tournament GUIDs across friends; crawl each once.
- **Person-merging stays deferred** to sub-project D (archive stores raw display
  names + profile GUIDs; no identity resolution here).

## Architecture — 4 units feeding the existing `archive_crawl.run()`

### 1. `archive_profile.py` (new, pure parser)
`parse_profile_tournaments(html) -> list[dict]` →
`[{"id": tournament_guid, "name": str, "start_date": iso|None}]`.
Parses the server-rendered profile page's tournament links; skips the header/profile
card (no dates/draws). De-duped by GUID. **Fixture-tested** against a sanitized real
capture.

### 2. `archive_parse.py` (REWRITE the bracket parser)
Replace the `bracket-round__title`-based `_BracketParser` / `parse_bracket` with:

`parse_matches_page(html) -> list[dict]`, one dict per match:
```
{ "draw_id": "GUID:N", "draw_name": str,
  "round_label": str, "round_index": int,       # reuse existing _round_index()
  "sides": [[{name, profile_guid, seed}], [...]],
  "winner_side": 1|2|None, "score_raw": "21-14 16-21 21-18"|None,
  "scheduled_iso": iso|None }
```
Keyed strictly on the real contract above. `_round_index()` is kept and extended if
new labels appear. `parse_draw_list` is retained (used for draw metadata / the old
tests) OR removed if unused after rewrite — decided at plan time. **Fixture-tested**
against a sanitized real `matches.aspx` fixture. The obsolete
`bracket_elimination.html` / `bracket_two_rounds.html` fixtures + their tests are
replaced by the real-markup fixture.

### 3. `archive_discover.py` (new, thin live driver, `# pragma: no cover`)
`discover_tournament_ids(fetch_fn, profile_guids) -> list[dict]`: fetch each
`/player-profile/{guid}` via the injected `fetch_fn` (so the raw-cache + politeness in
`archive_fetch` apply), parse with `archive_profile`, union by GUID. The GUID list is
read from `data/players.csv` by the caller, not hard-coded.

### 4. Wiring in `archive_crawl.py`
Add `crawl_from_profiles(*, delay_ms=700)` as a **sibling** to the dead `crawl_live`
(keep `crawl_live` for history, still `# pragma: no cover`). It:
1. opens a Playwright session (reusing `client.new_context`/`ensure_login`/
   `dismiss_cookies` and the `archive_fetch` getter);
2. `discover_tournament_ids(...)` → list of `{id, name, start_date}`;
3. calls the existing `run(conn, tournaments, fetch_fn, now)` but with a
   **matches-page** `process_tournament`: fetch `matches.aspx?id=GUID`,
   `parse_matches_page`, group rows by `draw_id`, `upsert_draw` (name from
   `draw_name`), `upsert_player` per side entrant (with `profile_guid`, `seed`),
   `insert_match`. Because `matches.aspx` is tournament-scoped, this replaces the
   per-draw fetch loop in the current `process_tournament`; the DB upsert calls are
   unchanged.
4. New CLI verb wiring so `archive-crawl --from-profiles` runs it (exact flag decided
   at plan time; must run from host with `.env`, uv only).

Politeness throughout: concurrency 1, `delay_ms >= 700`, backoff on error (the crawl
state machine already records per-tournament errors and continues).

## Privacy (rule #4 — PRIVACY IS THE ARCHITECTURE)

- The archive DB (`data/archive/archive.sqlite`) and raw cache live under `data/`
  (the private nested repo). Profile GUIDs may live there. **Nothing** flows to
  `web/*.json` or the public repo. Public build/export/site are **byte-for-byte
  unaffected** (asserted by re-running the existing public-privacy test + a build
  diff).
- **Committed fixtures are SANITIZED:** fake GUIDs, real names replaced with
  placeholders, mirroring `tests/fixtures/upcoming/profile_tournaments_live.html`.
  A test asserts no real profile GUID pattern from `data/players.csv` appears in any
  committed `tests/fixtures/` file. Raw captures are never committed.

## Testing

- **Pure parsers** (`archive_profile`, `parse_matches_page`): unit-tested against
  sanitized real fixtures — the ONLY way real-DOM correctness is proven. No guessed
  selectors: each fixture is derived from a real capture, then sanitized.
- **Live drivers** (`archive_discover`, `crawl_from_profiles`): `# pragma: no cover`
  thin wrappers; verified by one **human-run** live smoke crawl of a single friend
  at the end (evidence: DB row counts + one spot-checked bracket via `/api/archive`).
- `uv run ruff check` clean; **every "tests pass" claim is verified by re-running
  `uv run pytest` and reading output** (a prior subagent falsely reported passing —
  trust file content + git log, not reports).

## Out of scope (deferred)

- `draw.aspx` per-draw column geometry (v1 reconstructs rounds from labels).
- Non-core / opponent / low-confidence GUIDs (players_candidates.csv, people.csv).
- Person/identity merging (sub-project D).
- Scheduled auto-refresh (sub-project C).
- The bracket-visualization frontend (sub-project B) — it consumes this data next.

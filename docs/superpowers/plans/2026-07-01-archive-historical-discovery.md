# Archive Historical Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill the empty sub-project A archive with real historical tournaments discovered from core friends' profile pages and parsed from `matches.aspx`.

**Architecture:** Four units feed the already-shipped `archive_crawl.run()`. A new pure parser reads finished-tournament GUIDs from a friend's server-rendered `/player-profile/{guid}` page. A rewritten `archive_parse` reads every match (draw, round, sides, winner, score) from the tournament-scoped, server-rendered `/sport/matches.aspx?id=GUID` page. A thin live driver unions discovered GUIDs across the 9 core friends who have profile GUIDs; a new `crawl_from_profiles` wires discovery → matches-page fetch → the existing DB upserts. Public build/export/site are untouched.

**Tech Stack:** Python 3.13 via `uv`; stdlib `html.parser`/`re`; Playwright (existing `client.py`); SQLite (existing `archive_db.py`); pytest; ruff.

## Global Constraints

- **Python via `uv` only** — `uv run …`, never bare `pip`/`python`. On this machine the agent shell may lack `uv` on PATH; call `~/.local/bin/uv.exe` if `uv` is not found.
- **Lint:** `uv run ruff check` must be clean before any task is claimed done.
- **PRIVACY IS THE ARCHITECTURE (rule #4):** the archive DB + raw cache live ONLY under `data/`. Nothing flows to `web/*.json` or the public repo. Committed fixtures MUST be sanitized — fake GUIDs, placeholder names — like `tests/fixtures/upcoming/profile_tournaments_live.html`. Never commit a raw capture.
- **Verify, don't assert (rule #6):** every "tests pass" claim is backed by re-running `uv run pytest` and reading the output. Trust committed file content + `git log`, not subagent reports (a prior subagent falsely reported passing and clobbered shared git state).
- **Politeness (live only):** concurrency 1, `delay_ms >= 700`, errors recorded + skipped, never crash the loop.
- **Live scrapes run from the HOST** (container has no creds) with the env-shadowing fix: `unset TOURNAMENTSOFTWARE_USERNAME TOURNAMENTSOFTWARE_PASSWORD TOURNAMENTSOFTWARE_BASE_URL && ~/.local/bin/uv.exe run …` in ONE command.
- **Commit messages:** follow the repo convention (no `Co-Authored-By` trailer; recent history has none).

## Real DOM contract (verbatim from a 2026-07-01 live capture — do NOT guess)

`/sport/matches.aspx?id=GUID` is server-rendered; each match:
```
<li class="match-group__item">
  <div class="match match--list">
    <div class="match__header"><ul class="match__header-title">
      <li class="match__header-title-item">
        <a href="/sport/draw.aspx?id=GUID&draw=16"><span class="nav-link__value">MS C</span></a>
      </li>
      <li class="match__header-title-item">
        <span title="Final"><span class="nav-link__value">Final</span></span>
      </li>
    </ul></div>
    <div class="match__body"><div class="match__row-wrapper">
      <div class="match__row ">        <!-- side 1 -->
        <a href="/sport/player.aspx?id=GUID&player=9"><span class="nav-link__value">Xiaoran Chang</span></a>
      </div>
      <div class="match__row has-won"> <!-- side 2 = winner -->
        <a href="/sport/player.aspx?id=GUID&player=115"><span class="nav-link__value">Ilmari Saukkonen [3/4]</span></a>
      </div>
    </div>
    <div class="match__result">
      <ul class="points"><li class="points__cell "> 10 </li><li class="points__cell points__cell--won"> 21 </li></ul>
      <ul class="points"><li class="points__cell "> 6 </li><li class="points__cell points__cell--won"> 21 </li></ul>
    </div>
  </div>
</li>
```
Notes: `match-group__header` (a sticky time like "12.00") groups by TIME — ignore it. Draw id = `f"{GUID}:{N}"`. Round label from the `title=` attr of the 2nd `match__header-title-item`. Winner = the `match__row` carrying `has-won`. Seed is the trailing `[n]` / `[3/4]` in the name. Each `<ul class="points">` is one GAME; each `<li class="points__cell">` is one side's points that game, in row order (side1 first, side2 second). Doubles rows contain two `<a player.aspx>` anchors.

`/player-profile/{guid}` is server-rendered; finished tournaments appear as:
```
<a href="/sport/tournament?id=GUID" ...>Tournament Name</a>
```
(plus `/sport/draw.aspx?id=GUID&draw=N` links). The first/profile-header card has no tournament link and is naturally skipped by matching only `tournament?id=`.

---

## Task 1: `parse_matches_page` — pure parser for `matches.aspx`

**Files:**
- Modify: `src/badminton_tracker/archive_parse.py` (add `parse_matches_page`; keep `_round_index`, `parse_draw_list`; delete `_BracketParser`/`parse_bracket`)
- Create: `tests/fixtures/archive/matches_page.html` (SANITIZED faithful fixture)
- Modify: `tests/test_archive_parse.py` (replace `parse_bracket` tests; keep `_round_index` test + `parse_draw_list` test)
- Delete: `tests/fixtures/archive/bracket_elimination.html`, `tests/fixtures/archive/bracket_two_rounds.html`

**Interfaces:**
- Consumes: existing `_round_index(label) -> int`.
- Produces: `parse_matches_page(html: str) -> list[dict]`, one dict per match:
  ```
  {"draw_id": "GUID:N", "draw_name": str,
   "round_label": str, "round_index": int, "position": int,
   "sides": [[{"name": str, "profile_guid": str, "seed": int|None}], [...]],
   "winner_side": 1|2|None, "score_raw": str|None, "scheduled_iso": None}
  ```
  `position` increments per (draw_id, round_label) group, resetting when either changes. `score_raw` is side1-side2 space-joined games, e.g. `"10-21 6-21"`; `None` if no `points` cells. `scheduled_iso` stays `None` (time is only a clock on this page; date lives elsewhere — deferred).

- [ ] **Step 1: Create the sanitized fixture** `tests/fixtures/archive/matches_page.html`

```html
<!--
  SANITIZED faithful snapshot of a real /sport/matches.aspx?id=GUID page from
  badmintonfinland.tournamentsoftware.com (captured 2026-07-01). GUIDs are FAKE
  and names are placeholders (this file is committed to the PUBLIC repo).
  Exercises the real DOM: time-grouped match-group headers (ignored), per-match
  draw+round header (match__header-title), winner via match__row has-won, seeds
  in trailing [n], doubles rows with two player anchors, per-game points cells.
-->
<div class="content">
  <li class="match-group__item">
    <div class="match-group__wrapper">
      <h5 class="sticky is-sticky match-group__header"> 12.00 </h5>
      <ol class="match-group">

        <!-- Singles Final: side2 wins 21-10 21-6 -->
        <li class="match-group__item">
          <div class="match match--list">
            <div class="match__header"><ul class="match__header-title">
              <li class="match__header-title-item">
                <a href="/sport/draw.aspx?id=AAAA1111-1111-1111-1111-111111111111&amp;draw=16" class="nav-link"><span class="nav-link__value">MS C</span></a>
              </li>
              <li class="match__header-title-item">
                <span title="Final" class="nav-link"><span class="nav-link__value">Final</span></span>
              </li>
            </ul></div>
            <div class="match__body"><div class="match__row-wrapper">
              <div class="match__row ">
                <div class="match__row-title"><div class="match__row-title-value"><span class="match__row-title-value-content">
                  <a href="/sport/player.aspx?id=AAAA1111-1111-1111-1111-111111111111&amp;player=9" class="nav-link"><span class="nav-link__value">Alpha One</span></a>
                </span></div></div>
              </div>
              <div class="match__row has-won">
                <div class="match__row-title"><div class="match__row-title-value"><span class="match__row-title-value-content">
                  <a href="/sport/player.aspx?id=AAAA1111-1111-1111-1111-111111111111&amp;player=115" class="nav-link"><span class="nav-link__value">Beta Two [3/4]</span></a>
                </span></div></div>
                <span class="tag--round tag--success tag tag--small match__status">V</span>
              </div>
            </div>
            <div class="match__result">
              <ul class="points"><li class="points__cell "> 10 </li><li class="points__cell points__cell--won"> 21 </li></ul>
              <ul class="points"><li class="points__cell "> 6 </li><li class="points__cell points__cell--won"> 21 </li></ul>
            </div></div>
          </div>
        </li>

        <!-- Doubles Semi final: side1 (two players) wins 21-15 21-18 -->
        <li class="match-group__item">
          <div class="match match--list">
            <div class="match__header"><ul class="match__header-title">
              <li class="match__header-title-item">
                <a href="/sport/draw.aspx?id=AAAA1111-1111-1111-1111-111111111111&amp;draw=16" class="nav-link"><span class="nav-link__value">MS C</span></a>
              </li>
              <li class="match__header-title-item">
                <span title="Semi final" class="nav-link"><span class="nav-link__value">Semi final</span></span>
              </li>
            </ul></div>
            <div class="match__body"><div class="match__row-wrapper">
              <div class="match__row has-won">
                <div class="match__row-title"><div class="match__row-title-value"><span class="match__row-title-value-content">
                  <a href="/sport/player.aspx?id=AAAA1111-1111-1111-1111-111111111111&amp;player=9" class="nav-link"><span class="nav-link__value">Alpha One</span></a>
                </span></div></div>
                <div class="match__row-title"><div class="match__row-title-value"><span class="match__row-title-value-content">
                  <a href="/sport/player.aspx?id=AAAA1111-1111-1111-1111-111111111111&amp;player=42" class="nav-link"><span class="nav-link__value">Gamma Three</span></a>
                </span></div></div>
                <span class="tag--round tag--success tag tag--small match__status">V</span>
              </div>
              <div class="match__row ">
                <div class="match__row-title"><div class="match__row-title-value"><span class="match__row-title-value-content">
                  <a href="/sport/player.aspx?id=AAAA1111-1111-1111-1111-111111111111&amp;player=77" class="nav-link"><span class="nav-link__value">Delta Four</span></a>
                </span></div></div>
              </div>
            </div>
            <div class="match__result">
              <ul class="points"><li class="points__cell points__cell--won"> 21 </li><li class="points__cell "> 15 </li></ul>
              <ul class="points"><li class="points__cell points__cell--won"> 21 </li><li class="points__cell "> 18 </li></ul>
            </div></div>
          </div>
        </li>

      </ol>
    </div>
  </li>
</div>
```

- [ ] **Step 2: Write the failing test** — add to `tests/test_archive_parse.py`

```python
def test_parse_matches_page_singles_final_with_score_and_winner():
    html = (FIX / "matches_page.html").read_text(encoding="utf-8")
    matches = archive_parse.parse_matches_page(html)
    final = next(m for m in matches if m["round_label"] == "Final")
    assert final["draw_id"] == "AAAA1111-1111-1111-1111-111111111111:16"
    assert final["draw_name"] == "MS C"
    assert final["round_index"] == 0
    assert final["position"] == 0
    assert [[p["name"] for p in s] for s in final["sides"]] == [["Alpha One"], ["Beta Two"]]
    assert final["sides"][1][0]["seed"] == 3            # "[3/4]" -> first number
    assert final["sides"][0][0]["profile_guid"] == "AAAA1111-1111-1111-1111-111111111111:9"
    assert final["winner_side"] == 2
    assert final["score_raw"] == "10-21 6-21"           # side1-side2 per game


def test_parse_matches_page_doubles_semi_two_players_side1_wins():
    html = (FIX / "matches_page.html").read_text(encoding="utf-8")
    matches = archive_parse.parse_matches_page(html)
    semi = next(m for m in matches if m["round_label"] == "Semi final")
    assert semi["round_index"] == 1
    assert [len(s) for s in semi["sides"]] == [2, 1]     # side1 doubles, side2 single (fixture)
    assert [p["name"] for p in semi["sides"][0]] == ["Alpha One", "Gamma Three"]
    assert semi["winner_side"] == 1
    assert semi["score_raw"] == "21-15 21-18"
```

Remove `test_parse_bracket_final_with_winner` and `test_parse_bracket_multi_round_positions_and_ordering` (they target the deleted `parse_bracket` + deleted fixtures). Keep `test_parse_draw_list` and `test_round_index_orders_real_labels`.

- [ ] **Step 3: Run test to verify it fails**

Run: `~/.local/bin/uv.exe run pytest tests/test_archive_parse.py -v`
Expected: the two new tests FAIL with `AttributeError: module 'badminton_tracker.archive_parse' has no attribute 'parse_matches_page'`.

- [ ] **Step 4: Implement `parse_matches_page`; delete `_BracketParser`/`parse_bracket`**

In `src/badminton_tracker/archive_parse.py`, keep the module docstring, `_round_index` and its regexes, and `parse_draw_list`. Delete `_BracketParser` and `parse_bracket`. Add:

```python
_DRAW_HREF_RE = re.compile(r"draw\.aspx\?id=([0-9A-Fa-f-]{36})&(?:amp;)?draw=(\d+)", re.I)
_PLAYER_HREF_RE = re.compile(r"player\.aspx\?id=([0-9A-Fa-f-]{36})&(?:amp;)?player=(\d+)", re.I)
_NAME_RE = re.compile(r'nav-link__value">(.*?)</span>', re.S)
_SEED_RE = re.compile(r"\[(\d+)")
_MATCH_ITEM_RE = re.compile(r'<div class="match match--list">(.*?)(?=<div class="match match--list">|</ol>|$)', re.S)


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def parse_matches_page(html: str) -> list[dict]:
    """Parse a tournament-scoped /sport/matches.aspx page into per-match dicts.

    Each match self-describes its draw + round via match__header-title; winner is
    the match__row carrying has-won; score is per-game points cells (side1 first).
    """
    out: list[dict] = []
    positions: dict[tuple[str, str], int] = {}
    for block_m in _MATCH_ITEM_RE.finditer(html):
        block = block_m.group(0)
        header, _, rest = block.partition('class="match__body"')

        dm = _DRAW_HREF_RE.search(header)
        if not dm:
            continue
        draw_id = f"{dm.group(1)}:{dm.group(2)}"
        # draw name = first nav-link__value inside the header
        hn = _NAME_RE.search(header)
        draw_name = _clean(hn.group(1)) if hn else ""
        # round label = title="..." on the 2nd header-title-item
        titles = re.findall(r'title="([^"]+)"', header)
        round_label = titles[0] if titles else ""

        sides: list[list[dict]] = []
        winner_side: int | None = None
        for rm in re.finditer(r'<div class="match__row( has-won)?\s*">(.*?)(?=<div class="match__row|<div class="match__result"|$)', rest, re.S):
            is_win = bool(rm.group(1))
            row = rm.group(2)
            entrants: list[dict] = []
            for pm in _PLAYER_HREF_RE.finditer(row):
                guid, player_no = pm.group(1), pm.group(2)
                # the name span follows this anchor
                after = row[pm.end():]
                nm = _NAME_RE.search(after)
                raw_name = _clean(nm.group(1)) if nm else ""
                seed_m = _SEED_RE.search(raw_name)
                name = re.sub(r"\s*\[.*?\]\s*$", "", raw_name).strip()
                entrants.append({
                    "name": name,
                    "profile_guid": f"{guid}:{player_no}",
                    "seed": int(seed_m.group(1)) if seed_m else None,
                })
            if not entrants:
                continue
            sides.append(entrants)
            if is_win:
                winner_side = len(sides)

        if not sides:
            continue

        # score: one <ul class="points"> per game; two cells (side1, side2)
        games: list[str] = []
        result_seg = rest.partition('class="match__result"')[2]
        for ul in re.finditer(r'<ul class="points">(.*?)</ul>', result_seg, re.S):
            cells = re.findall(r'points__cell[^>]*>\s*([0-9]+)\s*<', ul.group(1))
            if len(cells) >= 2:
                games.append(f"{cells[0]}-{cells[1]}")
        score_raw = " ".join(games) if games else None

        key = (draw_id, round_label)
        pos = positions.get(key, 0)
        positions[key] = pos + 1
        out.append({
            "draw_id": draw_id,
            "draw_name": draw_name,
            "round_label": round_label,
            "round_index": _round_index(round_label),
            "position": pos,
            "sides": sides,
            "winner_side": winner_side,
            "score_raw": score_raw,
            "scheduled_iso": None,
        })
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `~/.local/bin/uv.exe run pytest tests/test_archive_parse.py -v`
Expected: all tests PASS (2 new + `parse_draw_list` + `_round_index`).

- [ ] **Step 6: Lint**

Run: `~/.local/bin/uv.exe run ruff check src/badminton_tracker/archive_parse.py tests/test_archive_parse.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add src/badminton_tracker/archive_parse.py tests/test_archive_parse.py tests/fixtures/archive/matches_page.html
git rm tests/fixtures/archive/bracket_elimination.html tests/fixtures/archive/bracket_two_rounds.html
git commit -m "feat(archive): parse matches.aspx (real DOM) replacing wrong bracket parser"
```

---

## Task 2: `parse_profile_tournaments` — pure parser for `/player-profile/{guid}`

**Files:**
- Create: `src/badminton_tracker/archive_profile.py`
- Create: `tests/fixtures/archive/profile_history.html` (SANITIZED)
- Create: `tests/test_archive_profile.py`

**Interfaces:**
- Produces: `parse_profile_tournaments(html: str) -> list[dict]`, each
  `{"id": tournament_guid, "name": str, "start_date": None}`. De-duped by GUID
  (case-insensitive), first-seen order. `start_date` is `None` for now (profile
  cards' date shape is deferred; `run()` tolerates `None`).

- [ ] **Step 1: Create the sanitized fixture** `tests/fixtures/archive/profile_history.html`

```html
<!--
  SANITIZED faithful snapshot of a real /player-profile/{guid} page (captured
  2026-07-01). FAKE GUIDs. The first card is the profile header (no tournament
  link) and must be skipped. Finished tournaments appear as /sport/tournament?id=
  links; each also has draw links (not needed for discovery).
-->
<div class="content">
  <div class="module module--card">   <!-- profile header: NO tournament link -->
    <h4 class="media__title"><a href="/sport/player.aspx?id=AAAA1111-1111-1111-1111-111111111111&amp;player=58" class="media__link"><span class="nav-link__value">Friend Name</span></a></h4>
  </div>

  <div class="module module--card">
    <h4 class="media__title"><a href="/sport/tournament?id=BBBB2222-2222-2222-2222-222222222222" class="media__link"><span class="nav-link__value">Spring Open 2025</span></a></h4>
    <a href="/sport/draw.aspx?id=BBBB2222-2222-2222-2222-222222222222&amp;draw=4" class="nav-link"><span class="nav-link__value">MS C</span></a>
  </div>

  <div class="module module--card">
    <h4 class="media__title"><a href="/sport/tournament?id=CCCC3333-3333-3333-3333-333333333333" class="media__link"><span class="nav-link__value">Winter Cup 2021</span></a></h4>
    <a href="/sport/draw.aspx?id=CCCC3333-3333-3333-3333-333333333333&amp;draw=2" class="nav-link"><span class="nav-link__value">MD C</span></a>
  </div>

  <!-- duplicate link to the same tournament elsewhere on the page -->
  <a href="/sport/tournament?id=BBBB2222-2222-2222-2222-222222222222">Spring Open 2025</a>
</div>
```

- [ ] **Step 2: Write the failing test** `tests/test_archive_profile.py`

```python
from pathlib import Path

from badminton_tracker import archive_profile

FIX = Path(__file__).parent / "fixtures" / "archive"


def test_parse_profile_tournaments_finds_finished_deduped_skips_header():
    html = (FIX / "profile_history.html").read_text(encoding="utf-8")
    tours = archive_profile.parse_profile_tournaments(html)
    ids = [t["id"] for t in tours]
    # profile-header card (player.aspx only) is skipped; both tournaments found once
    assert ids == ["BBBB2222-2222-2222-2222-222222222222",
                   "CCCC3333-3333-3333-3333-333333333333"]
    assert tours[0]["name"] == "Spring Open 2025"
    assert tours[0]["start_date"] is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `~/.local/bin/uv.exe run pytest tests/test_archive_profile.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'badminton_tracker.archive_profile'`.

- [ ] **Step 4: Implement** `src/badminton_tracker/archive_profile.py`

```python
"""Pure parser: a friend's /player-profile/{guid} page -> finished tournaments.

Server-rendered; no network here. The profile-header card links to player.aspx
only, so matching on tournament?id= naturally skips it. Discovery source for the
historical archive crawl (see docs/superpowers/specs/2026-07-01-archive-...).
"""

from __future__ import annotations

import re

_TOUR_RE = re.compile(
    r'<a[^>]*href="[^"]*/sport/tournament\?id=([0-9A-Fa-f-]{36})"[^>]*>(.*?)</a>',
    re.I | re.S,
)


def parse_profile_tournaments(html: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for m in _TOUR_RE.finditer(html):
        guid = m.group(1)
        if guid.lower() in seen:
            continue
        seen.add(guid.lower())
        name = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        out.append({"id": guid, "name": name, "start_date": None})
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `~/.local/bin/uv.exe run pytest tests/test_archive_profile.py -v`
Expected: PASS.

- [ ] **Step 6: Lint**

Run: `~/.local/bin/uv.exe run ruff check src/badminton_tracker/archive_profile.py tests/test_archive_profile.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add src/badminton_tracker/archive_profile.py tests/test_archive_profile.py tests/fixtures/archive/profile_history.html
git commit -m "feat(archive): parse finished tournaments from a player-profile page"
```

---

## Task 3: Sanitized-fixture privacy guard

**Files:**
- Modify: `tests/test_archive_privacy.py`

**Interfaces:**
- Consumes: the two committed fixtures from Tasks 1–2.
- Produces: a test asserting no REAL profile GUID (from `data/players.csv`) appears in any committed `tests/fixtures/` file.

- [ ] **Step 1: Write the failing-then-passing test** — add to `tests/test_archive_privacy.py`

```python
def test_committed_fixtures_contain_no_real_profile_guids():
    import csv
    root = Path(config.__file__).resolve().parents[2]
    players = root / "data" / "players.csv"
    if not players.exists():
        return  # private data repo not present; skip
    real = set()
    with players.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            g = (row.get("profile_guid") or "").strip().lower()
            if g:
                real.add(g)
    if not real:
        return
    fixtures = (root / "tests" / "fixtures").rglob("*.html")
    for fx in fixtures:
        text = fx.read_text(encoding="utf-8").lower()
        for g in real:
            assert g not in text, f"REAL profile GUID {g} leaked into {fx}"
```

- [ ] **Step 2: Run the test**

Run: `~/.local/bin/uv.exe run pytest tests/test_archive_privacy.py -v`
Expected: PASS (the Task 1–2 fixtures use FAKE GUIDs). If it FAILS, a fixture was not sanitized — fix the fixture, do not weaken the test.

- [ ] **Step 3: Lint + full suite**

Run: `~/.local/bin/uv.exe run ruff check tests/test_archive_privacy.py && ~/.local/bin/uv.exe run pytest -q`
Expected: ruff clean; whole suite green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_archive_privacy.py
git commit -m "test(archive): guard committed fixtures against real profile GUIDs"
```

---

## Task 4: `archive_discover` — thin live discovery driver

**Files:**
- Create: `src/badminton_tracker/archive_discover.py`
- Create: `tests/test_archive_discover.py`

**Interfaces:**
- Consumes: `archive_profile.parse_profile_tournaments`.
- Produces:
  - `core_profile_guids(csv_path=None) -> list[str]` — profile GUIDs of core friends from `data/players.csv` (rows with a non-empty `profile_guid`).
  - `discover_tournament_ids(fetch_fn, profile_guids, base_url) -> list[dict]` — for each guid, `fetch_fn(f"{base_url}/player-profile/{guid}")`, parse, union by tournament GUID (first-seen order). `fetch_fn(url) -> str`.

- [ ] **Step 1: Write the failing test** `tests/test_archive_discover.py`

```python
from badminton_tracker import archive_discover


def test_discover_unions_tournaments_across_profiles_dedup():
    pages = {
        "http://b/player-profile/g1":
            '<a href="/sport/tournament?id=BBBB2222-2222-2222-2222-222222222222">A 2025</a>',
        "http://b/player-profile/g2":
            '<a href="/sport/tournament?id=BBBB2222-2222-2222-2222-222222222222">A 2025</a>'
            '<a href="/sport/tournament?id=CCCC3333-3333-3333-3333-333333333333">B 2024</a>',
    }
    calls = []

    def fetch_fn(url):
        calls.append(url)
        return pages[url]

    out = archive_discover.discover_tournament_ids(fetch_fn, ["g1", "g2"], "http://b")
    ids = [t["id"] for t in out]
    assert ids == ["BBBB2222-2222-2222-2222-222222222222",
                   "CCCC3333-3333-3333-3333-333333333333"]
    assert calls == ["http://b/player-profile/g1", "http://b/player-profile/g2"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/bin/uv.exe run pytest tests/test_archive_discover.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement** `src/badminton_tracker/archive_discover.py`

```python
"""Discover finished-tournament GUIDs from core friends' profile pages.

The profile page is server-rendered, so a plain fetch (the injected fetch_fn,
which applies the raw-cache + politeness of archive_fetch) suffices. Pure union
logic is unit-tested; the live wiring lives in archive_crawl.crawl_from_profiles.
"""

from __future__ import annotations

import csv
from pathlib import Path

from . import archive_profile
from .config import DATA_DIR


def core_profile_guids(csv_path: Path | None = None) -> list[str]:
    path = csv_path or (DATA_DIR / "players.csv")
    if not path.exists():
        return []
    guids: list[str] = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            g = (row.get("profile_guid") or "").strip()
            if g:
                guids.append(g)
    return guids


def discover_tournament_ids(fetch_fn, profile_guids, base_url) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for guid in profile_guids:
        html = fetch_fn(f"{base_url}/player-profile/{guid}")
        for t in archive_profile.parse_profile_tournaments(html):
            key = t["id"].lower()
            if key not in seen:
                seen.add(key)
                out.append(t)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/bin/uv.exe run pytest tests/test_archive_discover.py -v`
Expected: PASS.

- [ ] **Step 5: Lint**

Run: `~/.local/bin/uv.exe run ruff check src/badminton_tracker/archive_discover.py tests/test_archive_discover.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/badminton_tracker/archive_discover.py tests/test_archive_discover.py
git commit -m "feat(archive): discover tournament GUIDs from core friends' profiles"
```

---

## Task 5: `process_matches_tournament` + `crawl_from_profiles` wiring

**Files:**
- Modify: `src/badminton_tracker/archive_crawl.py`
- Modify: `tests/test_archive_crawl.py` (add a test for the matches-page processor with a fake fetch_fn)

**Interfaces:**
- Consumes: `archive_parse.parse_matches_page`, `archive_discover.*`, existing `archive_db.*`, existing `run(conn, tournaments, fetch_fn, now)`.
- Produces:
  - `process_matches_tournament(conn, tid, fetch_fn, now)` — fetch `matches.aspx?id=tid`, parse, group by `draw_id`, upsert draws/players, insert matches. Signature-compatible so it can be passed where `run` expects a processor.
  - `crawl_from_profiles(*, delay_ms=700) -> dict` — `# pragma: no cover` live driver (discovery → run with the matches processor). Keeps the dead `crawl_live` untouched for history.
- Note: `run()` currently hard-calls the module-level `process_tournament`. To let `run` use the matches processor **without changing `run`'s public behavior**, add an optional param `processor=process_tournament` to `run` and call `processor(conn, tid, fetch_fn, now)`. Existing callers/tests are unaffected (default preserved).

- [ ] **Step 1: Write the failing test** — add to `tests/test_archive_crawl.py`

```python
from badminton_tracker import archive_crawl, archive_db


def test_process_matches_tournament_stores_draws_players_matches(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")
    tid = "AAAA1111-1111-1111-1111-111111111111"
    archive_db.upsert_tournament(conn, {
        "id": tid, "name": "T", "year": 2025, "start_date": None, "end_date": None,
        "location": None, "region": None, "category": None,
        "source_url": "u", "fetched_at": "now",
    })
    from pathlib import Path
    fx = Path(__file__).parent / "fixtures" / "archive" / "matches_page.html"
    html = fx.read_text(encoding="utf-8")

    def fetch_fn(url):
        assert "matches.aspx" in url and tid in url
        return html

    archive_crawl.process_matches_tournament(conn, tid, fetch_fn, "now")

    draws = conn.execute("SELECT * FROM draws").fetchall()
    assert [d["id"] for d in draws] == ["AAAA1111-1111-1111-1111-111111111111:16"]
    assert draws[0]["name"] == "MS C"
    matches = conn.execute(
        "SELECT round_label, score_raw, winner_side FROM matches ORDER BY round_index"
    ).fetchall()
    labels = [m["round_label"] for m in matches]
    assert "Final" in labels and "Semi final" in labels
    final = next(m for m in matches if m["round_label"] == "Final")
    assert final["score_raw"] == "10-21 6-21"
    assert final["winner_side"] == 2
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/bin/uv.exe run pytest tests/test_archive_crawl.py::test_process_matches_tournament_stores_draws_players_matches -v`
Expected: FAIL with `AttributeError: ... has no attribute 'process_matches_tournament'`.

- [ ] **Step 3: Implement** — in `src/badminton_tracker/archive_crawl.py`

Add the matches-page URL helper + processor, and make `run` take an optional `processor`:

```python
def _matches_url(tid: str) -> str:
    return f"{BASE_URL}/sport/matches.aspx?id={tid}"


def process_matches_tournament(conn, tid: str, fetch_fn, now: str) -> None:
    """Fetch matches.aspx for one tournament; store all draws + matches + players."""
    html = fetch_fn(_matches_url(tid))
    parsed = archive_parse.parse_matches_page(html)

    # upsert each distinct draw once, preserving first-seen order for `ordering`
    draw_order: dict[str, int] = {}
    for m in parsed:
        if m["draw_id"] not in draw_order:
            draw_order[m["draw_id"]] = len(draw_order)
            archive_db.upsert_draw(conn, {
                "id": m["draw_id"],
                "tournament_id": tid,
                "name": m["draw_name"],
                "draw_type": "unknown",
                "ordering": draw_order[m["draw_id"]],
            })

    for m in parsed:
        side_ids: list[list[int]] = [[], []]
        for i, side in enumerate(m["sides"][:2]):
            for pl in side:
                pid = archive_db.upsert_player(conn, {
                    "tournament_id": tid,
                    "display_name": pl["name"],
                    "profile_guid": pl.get("profile_guid"),
                    "club": None,
                    "seed": pl.get("seed"),
                })
                side_ids[i].append(pid)
        archive_db.insert_match(conn, {
            "draw_id": m["draw_id"],
            "round_label": m["round_label"],
            "round_index": m["round_index"],
            "position": m["position"],
            "side1_player_ids": side_ids[0],
            "side2_player_ids": side_ids[1],
            "score_raw": m["score_raw"],
            "winner_side": m["winner_side"],
            "scheduled_iso": m["scheduled_iso"],
            "court": None,
        })
```

Change `run`'s signature and its single processor call:

```python
def run(conn, tournament_ids: list[dict], fetch_fn, now: str,
        processor=process_tournament) -> dict:
```
and inside the loop replace `process_tournament(conn, tid, fetch_fn, now)` with
`processor(conn, tid, fetch_fn, now)`.

Add the live driver (mirrors `crawl_live`'s Playwright setup):

```python
def crawl_from_profiles(*, delay_ms: int = 700) -> dict:  # pragma: no cover
    """Discover tournaments from core friends' profiles, then crawl matches.aspx.

    Run from the HOST (.env creds); the container has none. Politeness: delay_ms.
    """
    import datetime as dt

    from playwright.sync_api import sync_playwright

    from . import archive_discover, archive_fetch, client

    now = dt.datetime.now(dt.UTC).isoformat()
    conn = archive_db.connect()
    p = sync_playwright().start()
    browser, ctx = client.new_context(p, headless=True)
    try:
        page = client.ensure_login(ctx)

        def getter(url: str) -> tuple[str, int]:
            page.goto(url, wait_until="domcontentloaded")
            client.dismiss_cookies(page)
            page.wait_for_timeout(400)
            return page.content(), 200

        def fetch_fn(url: str) -> str:
            return archive_fetch.fetch(conn, url, getter, now, delay_ms=delay_ms)

        guids = archive_discover.core_profile_guids()
        tournaments = archive_discover.discover_tournament_ids(fetch_fn, guids, BASE_URL)
        return run(conn, tournaments, fetch_fn, now, processor=process_matches_tournament)
    finally:
        ctx.close()
        browser.close()
        p.stop()
        conn.close()
```

Ensure the module imports `archive_parse` (already imported) and `BASE_URL` (already imported).

- [ ] **Step 4: Run the new test + the existing crawl tests**

Run: `~/.local/bin/uv.exe run pytest tests/test_archive_crawl.py -v`
Expected: the new test PASSES and all pre-existing crawl tests still PASS (the `processor` default preserves old behavior).

- [ ] **Step 5: Lint**

Run: `~/.local/bin/uv.exe run ruff check src/badminton_tracker/archive_crawl.py tests/test_archive_crawl.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/badminton_tracker/archive_crawl.py tests/test_archive_crawl.py
git commit -m "feat(archive): crawl_from_profiles via matches.aspx processor"
```

---

## Task 6: CLI verb `--from-profiles` + full-suite/privacy verification

**Files:**
- Modify: `src/badminton_tracker/__main__.py` (add flag + dispatch)

**Interfaces:**
- Consumes: `archive_crawl.crawl_from_profiles`.
- Produces: `archive-crawl --from-profiles` runs the profile-seeded crawl.

- [ ] **Step 1: Add the flag** — in `__main__.py`, after the existing `p_arch.add_argument("--delay-ms", ...)` line (around line 53):

```python
    p_arch.add_argument(
        "--from-profiles", action="store_true",
        help="PRIVATE: discover finished tournaments from core friends' profiles "
             "(instead of the dead year-range enumeration)",
    )
```

- [ ] **Step 2: Dispatch** — replace the `elif args.command == "archive-crawl":` block (around lines 124–133) with:

```python
    elif args.command == "archive-crawl":
        if args.from_profiles:
            from .archive_crawl import crawl_from_profiles

            summary = crawl_from_profiles(delay_ms=args.delay_ms)
        else:
            from .archive_crawl import crawl_live

            summary = crawl_live(
                year_from=args.year_from,
                year_to=args.year_to,
                refresh_months=args.refresh_months,
                delay_ms=args.delay_ms,
            )
        print(f"archive-crawl: {summary}")
```

- [ ] **Step 3: Verify the CLI parses (no network)**

Run: `~/.local/bin/uv.exe run badminton archive-crawl --help`
Expected: help text lists `--from-profiles`. (Do NOT run the crawl here — that's the human live step.)

- [ ] **Step 4: Full suite + ruff + privacy**

Run: `~/.local/bin/uv.exe run ruff check && ~/.local/bin/uv.exe run pytest -q`
Expected: ruff clean; entire suite green (incl. `test_archive_privacy.py` and `test_no_archive_import_in_public_pipeline`).

- [ ] **Step 5: Public-site no-op check (rule #4)**

Run: `git status --porcelain web/` — expected: NO changes to `web/data.json` from any task in this plan. (Unrelated pre-existing `web/*` edits on the branch are fine but must not have been touched by these tasks.)

- [ ] **Step 6: Commit**

```bash
git add src/badminton_tracker/__main__.py
git commit -m "feat(archive): archive-crawl --from-profiles CLI verb"
```

---

## Task 7 (HUMAN, live): smoke-crawl one friend + verify the DB populates

This task is run by a human from the HOST (creds in `.env`); it is not automatable in CI. It is the go/no-go's final proof that the whole pipeline populates real data.

- [ ] **Step 1: Temporarily seed a single friend** to keep the first live run small.

Run a one-off (do NOT commit): crawl using just Tong's GUID by editing nothing — instead run a throwaway Python that calls `discover_tournament_ids` for one guid, then `run(..., processor=process_matches_tournament)`. Or, simplest: run the full verb but be ready to Ctrl-C after the first tournament completes:

```bash
cd g:/proj/badminton_bros
unset TOURNAMENTSOFTWARE_USERNAME TOURNAMENTSOFTWARE_PASSWORD TOURNAMENTSOFTWARE_BASE_URL \
  && ~/.local/bin/uv.exe run badminton archive-crawl --from-profiles --delay-ms 900
```

- [ ] **Step 2: Verify DB row counts**

Run:
```bash
~/.local/bin/uv.exe run python -c "from badminton_tracker import archive_db as d; c=d.connect(); print({t: c.execute(f'select count(*) from {t}').fetchone()[0] for t in ['tournaments','draws','players','matches']})"
```
Expected: non-zero counts for all four tables.

- [ ] **Step 3: Spot-check one bracket** via the authed endpoint or a direct query:

```bash
~/.local/bin/uv.exe run python -c "from badminton_tracker import archive_db as d; c=d.connect(); rows=c.execute('select round_label,score_raw,winner_side from matches where score_raw is not null limit 5').fetchall(); [print(dict(r)) for r in rows]"
```
Expected: real round labels + plausible scores (e.g. `21-x`) + winner_side in {1,2}.

- [ ] **Step 4: Privacy re-confirm** — the archive lives only under `data/`, and nothing leaked:

```bash
git status --porcelain web/          # expect no data.json change from this work
git -C data status --porcelain        # archive DB changes belong to the PRIVATE repo
```

- [ ] **Step 5: Commit the private archive** (in the PRIVATE `data/` repo only):

```bash
git -C data add archive/ && git -C data commit -m "archive: first historical crawl (profile-seeded)"
```

- [ ] **Step 6: Update context** — mark the archive as POPULATED in `context/INDEX.md` and the memory note, and record how many tournaments/matches landed.

---

## Self-Review

**Spec coverage:** archive_profile (T2) ✓; archive_parse rewrite to real matches.aspx contract (T1) ✓; archive_discover core-friend seed + union (T4) ✓; crawl_from_profiles wiring to run() (T5) ✓; CLI verb (T6) ✓; sanitized fixtures + privacy guard (T1/T2/T3) ✓; public-site no-op check (T6) ✓; human live smoke crawl (T7) ✓. Toni-identity caveat from the spec: the seed reads every GUID row in players.csv (T4); if Toni must be excluded, that's a one-line `data/players.csv` edit in the private repo, out of this plan's code scope — noted for the human at T7.

**Placeholder scan:** every code step shows full code; no TBD/TODO/"handle edge cases". ✓

**Type consistency:** `parse_matches_page` returns the dict shape consumed verbatim by `process_matches_tournament` (draw_id/draw_name/round_label/round_index/position/sides/winner_side/score_raw/scheduled_iso). `discover_tournament_ids` returns `{id,name,start_date}` — the exact shape `run()` upserts (`t["id"]`, `t.get("name")`, `t.get("start_date")`). `profile_guid` is stored as `"{guid}:{player_no}"` (a stable per-tournament entrant key; the raw GUID is its prefix) — consistent across T1/T5. ✓

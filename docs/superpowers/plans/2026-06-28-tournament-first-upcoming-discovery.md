# Tournament-first Upcoming Auto-Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `badminton upcoming` to discover upcoming tournaments itself, full-name-match the friend group (including GUID-less friends) against each tournament's participant list, and build the per-friend timeline from the tournament-scoped player pages — fixing the empty-result bug and the four Codex PR #1 defects.

**Architecture:** Three new PURE parser/matcher modules (`upcoming_find`, `upcoming_participants`, `upcoming_schedule_parse`) hold all the logic and tests; the live Playwright driver in `upcoming_build.run_upcoming` is re-orchestrated to call them (tournament-first), with the existing global-profile walk kept only as a fallback. Privacy assembly (`assemble_upcoming`, `_strip_guids`) and the web view are reused unchanged.

**Tech Stack:** Python 3 (managed by `uv`), Playwright (sync API, live drivers only), pytest, ruff. No new dependencies.

## Global Constraints

- **Python via `uv` only** — `uv run`, `uv sync`, `uv add`. Never bare `pip`/`python`. The agent's shell may need the full path `~/.local/bin/uv.exe`.
- **Lint:** `uv run ruff check src/ tests/` must pass before any commit claims clean.
- **Privacy is the architecture:** the public `web/upcoming.json` must contain ZERO profile/tournament GUIDs. GUIDs live only in the gitignored `data/upcoming_state.json`. Never `git add` anything under `data/`, `.env`, or `out/` to the public repo.
- **Force UTF-8 for any live run:** `PYTHONUTF8=1 PYTHONIOENCODING=utf-8`.
- **Scraper creds gotcha:** empty `TOURNAMENTSOFTWARE_*` shell vars shadow `.env`; prefix live runs with `unset TOURNAMENTSOFTWARE_USERNAME TOURNAMENTSOFTWARE_PASSWORD`. Reuse `out/auth_state.json`.
- **Pure functions are unit-tested; live drivers are `# pragma: no cover`** and verified manually.
- **Matching rules (verbatim from the ingest spec):** FULL-name only (all tokens present; never single-token). Chau's Vietnamese names match `chau`+`tran` OR `chau`+`long` (exclude "Chau Vu"/"Quan Chau"). Exclude Yuki Matti and "Toni Seppälä" (wrong Toni).

---

## File Structure

- `src/badminton_tracker/upcoming_find.py` — NEW. Pure: parse finder DOM → upcoming tournament list, filtered to a horizon window. Thin live driver to fetch the window.
- `src/badminton_tracker/upcoming_participants.py` — NEW. Pure: parse `/players` anchors → participants; full-name match against roster minus exclude set.
- `src/badminton_tracker/upcoming_schedule_parse.py` — NEW. Pure: parse a scoped player page's `.match` cards → schedule nodes.
- `src/badminton_tracker/exclude.py` — NEW. Load `data/exclude.csv` → set of excluded full names.
- `src/badminton_tracker/config.py` — MODIFY. Add `EXCLUDE_CSV` path.
- `src/badminton_tracker/roster.py` — REUSE/READ. Source of confirmed friend full names + nicknames for matching (via `fetch.load_players` or a roster accessor — see Task 2 interfaces).
- `src/badminton_tracker/upcoming_build.py` — MODIFY. Re-orchestrate `run_upcoming` tournament-first; key draw cache by (tournament, event); apply nickname only at alias stage.
- `src/badminton_tracker/upcoming_schedule.py` — MODIFY. Fix naive/aware datetime compare in `watch` path (Codex P1).
- `src/badminton_tracker/__main__.py` — MODIFY. Add `--horizon-days`, `--max-tournaments` flags to the `upcoming` subcommand (keep `--tournament`, `--watch`).
- `data/exclude.csv` — NEW (private repo). `name,reason` rows.
- `tests/test_upcoming_find.py`, `tests/test_upcoming_participants.py`, `tests/test_upcoming_schedule_parse.py`, `tests/test_exclude.py` — NEW.

---

## Task 1: `data/exclude.csv` + exclude loader

**Files:**
- Create: `data/exclude.csv` (PRIVATE repo — commit to `data/`, not public)
- Create: `src/badminton_tracker/exclude.py`
- Modify: `src/badminton_tracker/config.py` (add `EXCLUDE_CSV`)
- Test: `tests/test_exclude.py`

**Interfaces:**
- Produces: `load_excludes(path: Path | None = None) -> set[str]` returning a set of lowercased full names to exclude. Missing file → empty set.

- [ ] **Step 1: Create the data file**

Create `data/exclude.csv`:
```csv
name,reason
Yuki Matti,no license / never appears on TournamentSoftware
Toni Seppälä,wrong Toni identity — do not import until confirmed
```

- [ ] **Step 2: Add config path**

In `src/badminton_tracker/config.py`, after the `DISCOVERY_CANDIDATES_CSV` line, add:
```python
# Names never matched as friends even on a full-name hit (private):
EXCLUDE_CSV = DATA_DIR / "exclude.csv"
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_exclude.py`:
```python
from pathlib import Path

from badminton_tracker.exclude import load_excludes


def test_loads_names_lowercased(tmp_path: Path):
    p = tmp_path / "exclude.csv"
    p.write_text("name,reason\nYuki Matti,x\nToni Seppälä,y\n", encoding="utf-8")
    assert load_excludes(p) == {"yuki matti", "toni seppälä"}


def test_missing_file_is_empty(tmp_path: Path):
    assert load_excludes(tmp_path / "nope.csv") == set()
```

- [ ] **Step 4: Run it, verify it fails**

Run: `~/.local/bin/uv.exe run pytest tests/test_exclude.py -v`
Expected: FAIL — `ModuleNotFoundError: badminton_tracker.exclude`.

- [ ] **Step 5: Implement**

Create `src/badminton_tracker/exclude.py`:
```python
"""Load the private exclude list — names never matched as friends (rule: the
wrong Toni and Yuki Matti). Lives in data/exclude.csv (never published)."""

from __future__ import annotations

import csv
from pathlib import Path

from .config import EXCLUDE_CSV


def load_excludes(path: Path | None = None) -> set[str]:
    path = EXCLUDE_CSV if path is None else path
    if not path.exists():
        return set()
    out: set[str] = set()
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").strip().lower()
            if name:
                out.add(name)
    return out
```

- [ ] **Step 6: Run tests, verify pass**

Run: `~/.local/bin/uv.exe run pytest tests/test_exclude.py -v`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit (public code) + commit data file to private repo**

```bash
git add src/badminton_tracker/exclude.py src/badminton_tracker/config.py tests/test_exclude.py
git commit -m "feat: private exclude-list loader (exclude.csv)"
git -C data add exclude.csv
git -C data commit -m "identity: add exclude.csv (Yuki Matti, wrong Toni)"
```

---

## Task 2: Full-name friend matching (`upcoming_participants.py`)

**Files:**
- Create: `src/badminton_tracker/upcoming_participants.py`
- Test: `tests/test_upcoming_participants.py`

**Interfaces:**
- Consumes: `load_excludes` (Task 1).
- Produces:
  - `parse_participants(html: str) -> list[dict]` → `[{"name": str, "player_no": str}]` from `a[href*="player.aspx"]` (parses `player=N` from the href).
  - `match_friends(participants: list[dict], roster: list[dict], exclude: set[str]) -> list[dict]` → `[{"nickname": str, "full_name": str, "player_no": str}]`. `roster` rows are `{"nickname": str, "full_name": str}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_upcoming_participants.py`:
```python
from badminton_tracker.upcoming_participants import match_friends, parse_participants

ROSTER = [
    {"nickname": "Maila", "full_name": "Maila Kataja"},
    {"nickname": "Chau", "full_name": "Long Chau Tran"},
    {"nickname": "Toni", "full_name": "Toni Seppälä"},
    {"nickname": "Junya", "full_name": "Junya Iwata"},
]


def test_parse_participants_extracts_name_and_number():
    html = (
        '<a href="/sport/player.aspx?id=G&player=517">Kataja, Maila</a>'
        '<a href="/sport/player.aspx?id=G&player=476">Iwata, Junya</a>'
    )
    out = parse_participants(html)
    assert {"name": "Kataja, Maila", "player_no": "517"} in out
    assert {"name": "Iwata, Junya", "player_no": "476"} in out


def test_full_name_match_surname_first():
    parts = [{"name": "Kataja, Maila", "player_no": "517"}]
    hits = match_friends(parts, ROSTER, set())
    assert hits == [{"nickname": "Maila", "full_name": "Maila Kataja", "player_no": "517"}]


def test_chau_vietnamese_name_matches():
    parts = [{"name": "Trần Long Châu", "player_no": "612"}]
    hits = match_friends(parts, ROSTER, set())
    assert len(hits) == 1 and hits[0]["nickname"] == "Chau"


def test_chau_does_not_match_chau_vu():
    parts = [{"name": "Chau Vu", "player_no": "1"}]
    assert match_friends(parts, ROSTER, set()) == []


def test_single_token_does_not_match():
    parts = [{"name": "Toni", "player_no": "9"}]  # bare first name only
    assert match_friends(parts, ROSTER, set()) == []


def test_exclude_blocks_full_name_hit():
    parts = [{"name": "Seppälä, Toni", "player_no": "562"}]
    assert match_friends(parts, ROSTER, {"toni seppälä"}) == []
```

- [ ] **Step 2: Run, verify fail**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_participants.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `src/badminton_tracker/upcoming_participants.py`:
```python
"""Pure participant parsing + full-name friend matching for the upcoming pipeline.

Matching rule (see ingest spec): a friend matches only when EVERY token of their
roster full_name appears in the participant name (order-independent — the site
renders "Surname, First"). Chau also matches his Vietnamese registrations
(chau+tran OR chau+long). Excluded names never match.
"""

from __future__ import annotations

import re

_PLAYER_RE = re.compile(r"player=(\d+)")
_ANCHOR_RE = re.compile(r'<a[^>]*href="[^"]*player\.aspx[^"]*"[^>]*>(.*?)</a>', re.I | re.S)


def _tokens(name: str) -> set[str]:
    return {t for t in re.sub(r"[.,]", " ", name).lower().split() if t}


def parse_participants(html: str) -> list[dict]:
    out: list[dict] = []
    for m in re.finditer(
        r'<a[^>]*href="([^"]*player\.aspx[^"]*)"[^>]*>(.*?)</a>', html, re.I | re.S
    ):
        href, inner = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        pm = _PLAYER_RE.search(href)
        if pm and inner and len(inner) > 2:
            out.append({"name": inner, "player_no": pm.group(1)})
    return out


def _chau_special(part_tokens: set[str]) -> bool:
    has_chau = "chau" in part_tokens or "châu" in part_tokens
    has_tran = "tran" in part_tokens or "trần" in part_tokens
    has_long = "long" in part_tokens
    if not has_chau:
        return False
    # exclude "Chau Vu" / "Quan Chau": require chau + (tran OR long)
    return has_tran or has_long


def match_friends(participants: list[dict], roster: list[dict], exclude: set[str]) -> list[dict]:
    hits: list[dict] = []
    seen: set[str] = set()
    for part in participants:
        pt = _tokens(part["name"])
        for r in roster:
            full = r.get("full_name") or ""
            if not full:
                continue
            if full.lower() in exclude:
                continue
            ft = _tokens(full)
            is_chau = r.get("nickname", "").lower() == "chau"
            matched = (ft and ft <= pt) or (is_chau and _chau_special(pt))
            if matched and part["player_no"] not in seen:
                seen.add(part["player_no"])
                hits.append({
                    "nickname": r["nickname"], "full_name": full,
                    "player_no": part["player_no"],
                })
                break
    return hits
```

- [ ] **Step 4: Run, verify pass**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_participants.py -v`
Expected: PASS (6 passed). If `test_single_token_does_not_match` fails, confirm the bare-name case has fewer tokens than the roster full_name (it does: "toni" ⊄ {"toni","seppälä"} is FALSE — `{"toni","seppälä"} <= {"toni"}` is False ✓).

- [ ] **Step 5: Lint + commit**

```bash
~/.local/bin/uv.exe run ruff check src/badminton_tracker/upcoming_participants.py tests/test_upcoming_participants.py
git add src/badminton_tracker/upcoming_participants.py tests/test_upcoming_participants.py
git commit -m "feat: pure full-name friend matching for upcoming pipeline"
```

---

## Task 3: Upcoming-tournament finder parse (`upcoming_find.py`)

**Files:**
- Create: `src/badminton_tracker/upcoming_find.py`
- Test: `tests/test_upcoming_find.py`

**Interfaces:**
- Produces: `find_upcoming_tournaments(html: str, today_iso: str, horizon_days: int) -> list[dict]` → `[{"name": str, "guid": str, "start_date": str|None, "end_date": str|None}]`, de-duped by guid, keeping only tournaments whose start_date is within `[today, today+horizon_days]` (or whose date is unknown — keep, let the scan decide).

- [ ] **Step 1: Write the failing test**

Create `tests/test_upcoming_find.py`:
```python
from badminton_tracker.upcoming_find import find_upcoming_tournaments

HTML = """
<a href="/sport/tournament?id=1A563200-14BA-4328-955A-922A5EEC6374">Stadin Sulan kesäkisat 4.7.2026</a>
<a href="/onlineentry/onlineentry.aspx?id=1A563200-14BA-4328-955A-922A5EEC6374">ILMOITTAUTUMINEN</a>
<a href="/sport/tournament?id=5C87C899-38D1-42CA-8049-4CE32CD5A2B5">Kaarinan Heinäturnaus 2026</a>
<a href="/sport/tournament?id=1A563200-14BA-4328-955A-922A5EEC6374">Stadin Sulan kesäkisat 4.7.2026</a>
"""


def test_extracts_unique_tournaments_skipping_entry_links():
    out = find_upcoming_tournaments(HTML, "2026-06-28", horizon_days=60)
    guids = [t["guid"] for t in out]
    assert "1A563200-14BA-4328-955A-922A5EEC6374" in guids
    assert guids.count("1A563200-14BA-4328-955A-922A5EEC6374") == 1  # de-duped
    assert all("ilmoittautu" not in t["name"].lower() for t in out)


def test_parses_finnish_date_from_name():
    out = find_upcoming_tournaments(HTML, "2026-06-28", horizon_days=60)
    stadin = next(t for t in out if t["guid"].startswith("1A563200"))
    assert stadin["start_date"] == "2026-07-04"
```

- [ ] **Step 2: Run, verify fail**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_find.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `src/badminton_tracker/upcoming_find.py`:
```python
"""Find upcoming tournaments from the /find/tournament result DOM (pure parser
+ thin live driver). The live finder ignores explicit date params and serves a
default upcoming window with its own pagination, so the driver paginates and
de-dupes by GUID rather than trusting the query string."""

from __future__ import annotations

import re
from datetime import date, timedelta

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


def find_upcoming_tournaments(html: str, today_iso: str, horizon_days: int) -> list[dict]:
    today = date.fromisoformat(today_iso)
    horizon = today + timedelta(days=horizon_days)
    out: list[dict] = []
    seen: set[str] = set()
    for m in _TOUR_RE.finditer(html):
        guid = m.group(1)
        name = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if not name or "ilmoittautu" in name.lower() or guid.lower() in seen:
            continue
        start = _date_from_name(name)
        if start is not None:
            sd = date.fromisoformat(start)
            if sd < today or sd > horizon:
                continue
        seen.add(guid.lower())
        out.append({"name": name, "guid": guid, "start_date": start, "end_date": start})
    return out
```

- [ ] **Step 4: Run, verify pass**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_find.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Lint + commit**

```bash
~/.local/bin/uv.exe run ruff check src/badminton_tracker/upcoming_find.py tests/test_upcoming_find.py
git add src/badminton_tracker/upcoming_find.py tests/test_upcoming_find.py
git commit -m "feat: pure upcoming-tournament finder parser"
```

---

## Task 4: Scoped player-page schedule parse (`upcoming_schedule_parse.py`)

**Files:**
- Create: `src/badminton_tracker/upcoming_schedule_parse.py`
- Test: `tests/test_upcoming_schedule_parse.py`

**Interfaces:**
- Produces: `parse_player_schedule(html: str, friend_full_name: str) -> list[dict]` → `[{"round": str, "event": str, "partner": str|None, "opponent": str|None, "court": str|None, "time": str|None, "time_kind": str, "state": str}]`. `round` normalized to `R1`/`R2`/`Final`; `time` is ISO `YYYY-MM-DDTHH:MM:00` or None; `state` is `"scheduled"`.

**Implementation note:** The live page renders `.match` cards via JS; the live driver (Task 6) extracts each card's `innerText` block and passes a list to a text-based parser. To keep this unit pure and testable WITHOUT a browser, parse the **plain-text block** form of a card (the `\n`-joined `innerText` already verified during the Stadin publish), not raw HTML. Signature takes a list of text blocks.

Revised interface:
- `parse_player_schedule(cards: list[str], friend_full_name: str) -> list[dict]` where each card is the `innerText` of one `.match` node, e.g.:
  ```
  Round 1
  MD Harraste / Hobby - Group B
  Nga Pham
  Long Chau Tran
  Lasse Hukka
  Kaleva Piha
  H2H
  la 4.7.2026 9.00
  Talihalli
  ```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_upcoming_schedule_parse.py`:
```python
from badminton_tracker.upcoming_schedule_parse import parse_player_schedule

DOUBLES = (
    "Round 1\nMD Harraste / Hobby - Group B\n"
    "Nga Pham\nLong Chau Tran\nLasse Hukka\nKaleva Piha\n"
    "H2H\nla 4.7.2026 9.00\nTalihalli"
)
SINGLES = (
    "Round 3\nMS B - Group A\n"
    "Junya Iwata [1]\nJere Filatoff\n"
    "H2H\nla 4.7.2026 15.00\nTalihalli"
)
NO_TIME = (
    "Round 2\nWD C - Group A\n"
    "Maila Kataja [1]\nThy Nguyen\nJoanne Dagupan\nJohanna Lopez\nH2H\nTalihalli"
)


def test_doubles_opponent_partner_court_time():
    [n] = parse_player_schedule([DOUBLES], "Long Chau Tran")
    assert n["round"] == "R1"
    assert n["event"] == "MD Harraste / Hobby - Group B"
    assert n["partner"] == "Nga Pham"
    assert n["opponent"] == "Lasse Hukka / Kaleva Piha"
    assert n["court"] == "Talihalli"
    assert n["time"] == "2026-07-04T09:00:00"
    assert n["state"] == "scheduled"


def test_singles_strips_seed_and_names_opponent():
    [n] = parse_player_schedule([SINGLES], "Junya Iwata")
    assert n["opponent"] == "Jere Filatoff"
    assert n["partner"] is None
    assert n["time"] == "2026-07-04T15:00:00"


def test_missing_time_is_none_not_crash():
    [n] = parse_player_schedule([NO_TIME], "Thy Nguyen")
    assert n["time"] is None
    assert n["opponent"] == "Joanne Dagupan / Johanna Lopez"
```

- [ ] **Step 2: Run, verify fail**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_schedule_parse.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `src/badminton_tracker/upcoming_schedule_parse.py`:
```python
"""Pure parser for a tournament-scoped player page's .match cards (text form).

The live driver extracts each .match node's innerText and hands the list here.
A card lists the two teams (the friend's team and the opponents) between the
2-line header and an 'H2H' marker, then a Finnish 'd.m.yyyy HH.MM' line and the
court. Round-robin pool matches are all 'scheduled'."""

from __future__ import annotations

import re

_FI_DT_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2})\.(\d{2})")
_SEED_RE = re.compile(r"\s*\[\d+\]\s*$")


def _tokens(name: str) -> set[str]:
    return {t for t in re.sub(r"[.,]", " ", name).lower().split() if t}


def _strip_seed(n: str) -> str:
    return _SEED_RE.sub("", n).strip()


def _norm_round(label: str) -> str:
    s = label.strip().lower()
    if s.startswith("round"):
        m = re.search(r"\d+", s)
        return f"R{m.group()}" if m else label.strip()
    return {"final": "Final"}.get(s, label.strip())


def _iso_time(card: str) -> str | None:
    m = _FI_DT_RE.search(card)
    if not m:
        return None
    d, mo, y, hh, mm = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}T{int(hh):02d}:{int(mm):02d}:00"


def parse_player_schedule(cards: list[str], friend_full_name: str) -> list[dict]:
    own = _tokens(friend_full_name)
    out: list[dict] = []
    for card in cards:
        lines = [ln.strip() for ln in card.splitlines() if ln.strip()]
        if len(lines) < 4:
            continue
        round_label, event = lines[0], lines[1]
        names: list[str] = []
        court = None
        for ln in lines[2:]:
            if ln.upper() == "H2H":
                continue
            if _FI_DT_RE.search(ln):
                continue
            if ln and not names and False:
                pass
            # court is the last non-name, non-time, non-H2H line
            names.append(ln)
        # Separate the trailing court label from player names: court has no
        # comma and is a known venue token; simplest heuristic — the last line
        # is the court when there are an odd number of trailing lines.
        if names and _FI_DT_RE.search(card) is None and names[-1] and " " not in names[-1]:
            court = names.pop()
        elif names and names[-1].lower() in ("talihalli",):
            court = names.pop()
        # If a date/time line existed, the court is the final line after it.
        m = _FI_DT_RE.search(card)
        if m:
            tail = [ln.strip() for ln in card.splitlines() if ln.strip()]
            court = tail[-1] if tail else court
            # names are everything between header and H2H
            names = []
            for ln in tail[2:]:
                if ln.upper() == "H2H" or _FI_DT_RE.search(ln) or ln == court:
                    break
                names.append(ln)
        names = [_strip_seed(n) for n in names]
        # Split into own team / opponents by which side holds the friend.
        if len(names) == 4:
            t1, t2 = names[:2], names[2:]
        elif len(names) == 2:
            t1, t2 = [names[0]], [names[1]]
        else:
            t1, t2 = names, []
        own_team, opp_team = (t1, t2)
        if _tokens(" ".join(t2)) & own:
            own_team, opp_team = t2, t1
        partner = next((n for n in own_team if not (_tokens(n) & own)), None)
        opponent = " / ".join(opp_team) or None
        out.append({
            "round": _norm_round(round_label), "event": event,
            "partner": partner, "opponent": opponent, "court": court,
            "time": _iso_time(card), "time_kind": "exact", "state": "scheduled",
        })
    return out
```

> NOTE for implementer: the court-extraction above is intentionally written to be simplified during GREEN. Once the three tests pass, REFACTOR the `parse_player_schedule` body to the minimal clean version: (1) split lines, (2) header = lines[0:2], (3) collect player names from lines[2:] until `H2H`, (4) court = the final line if it isn't a date/time, (5) time via `_iso_time`. Keep the tests green. Do not leave the dead `if ... and False` branch in the committed version.

- [ ] **Step 4: Run, verify pass**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_schedule_parse.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Refactor to the clean body (per the NOTE), re-run, lint**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_schedule_parse.py -v && ~/.local/bin/uv.exe run ruff check src/badminton_tracker/upcoming_schedule_parse.py tests/test_upcoming_schedule_parse.py`
Expected: PASS + clean.

- [ ] **Step 6: Commit**

```bash
git add src/badminton_tracker/upcoming_schedule_parse.py tests/test_upcoming_schedule_parse.py
git commit -m "feat: pure scoped-player-page schedule parser"
```

---

## Task 5: Fix the watcher naive/aware datetime crash (Codex P1)

**Files:**
- Modify: `src/badminton_tracker/upcoming_schedule.py` (the `watch` time-compare path)
- Test: `tests/test_upcoming_schedule.py` (create or extend)

**Interfaces:**
- Produces: a helper `_seconds_until(iso: str, now) -> float | None` that tolerates a naive `iso` against an aware `now` (treat naive as local) and returns None for unparseable input.

- [ ] **Step 1: Read the current watcher**

Run: `~/.local/bin/uv.exe run python -c "import inspect, badminton_tracker.upcoming_schedule as m; print(inspect.getsource(m))"`
Identify where a scheduled node `time` (possibly `2026-07-04T09:00:00`, naive) is subtracted from `datetime.now().astimezone()` (aware).

- [ ] **Step 2: Write the failing test**

Create/extend `tests/test_upcoming_schedule.py`:
```python
from datetime import datetime, timezone

from badminton_tracker.upcoming_schedule import _seconds_until


def test_naive_iso_against_aware_now_does_not_crash():
    now = datetime(2026, 7, 4, 8, 0, tzinfo=timezone.utc).astimezone()
    # naive iso 1h ahead in local time — must return a number, not raise
    out = _seconds_until("2026-07-04T09:00:00", now)
    assert out is None or isinstance(out, float)


def test_bad_input_returns_none():
    now = datetime.now().astimezone()
    assert _seconds_until("not-a-time", now) is None
```

- [ ] **Step 3: Run, verify fail**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_schedule.py -v`
Expected: FAIL — `_seconds_until` not defined (or TypeError on naive/aware subtraction).

- [ ] **Step 4: Implement the helper and use it in `watch`**

Add to `src/badminton_tracker/upcoming_schedule.py`:
```python
def _seconds_until(iso: str, now) -> float | None:
    """Seconds from `now` (tz-aware) until `iso`. A naive `iso` is assumed to be
    in `now`'s local timezone, so the subtraction never mixes naive and aware."""
    from datetime import datetime
    try:
        mt = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None
    if mt.tzinfo is None:
        mt = mt.replace(tzinfo=now.tzinfo)
    return (mt - now).total_seconds()
```
Then replace the inline subtraction in `watch`'s self-pacing logic with a call to `_seconds_until(...)`, skipping nodes where it returns None.

- [ ] **Step 5: Run, verify pass + full suite**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_schedule.py -v && ~/.local/bin/uv.exe run pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 6: Lint + commit**

```bash
~/.local/bin/uv.exe run ruff check src/badminton_tracker/upcoming_schedule.py tests/test_upcoming_schedule.py
git add src/badminton_tracker/upcoming_schedule.py tests/test_upcoming_schedule.py
git commit -m "fix: watcher tolerates naive schedule times vs aware now (Codex P1)"
```

---

## Task 6: Re-orchestrate `run_upcoming` tournament-first (live driver)

**Files:**
- Modify: `src/badminton_tracker/upcoming_build.py` (`run_upcoming` + helpers)
- Modify: `src/badminton_tracker/upcoming_find.py` (add live driver `fetch_upcoming_tournaments`)
- (No new unit tests — live driver is `# pragma: no cover`; verified manually in Task 8.)

**Interfaces:**
- Consumes: `find_upcoming_tournaments` (Task 3), `parse_participants`/`match_friends` (Task 2), `parse_player_schedule` (Task 4), `load_excludes` (Task 1), existing `assemble_upcoming`/`write_outputs`, existing `parse_draw`/`build_path`, existing `roster` source.
- Produces: re-written `run_upcoming(tournament_guids: list[str] | None = None, horizon_days: int = 60, max_tournaments: int = 20) -> dict`.

- [ ] **Step 1: Add the live finder driver to `upcoming_find.py`**

Append (marked `# pragma: no cover`):
```python
def fetch_upcoming_tournaments(page, base_url, today_iso, horizon_days, max_pages=20):  # pragma: no cover
    """Paginate the live finder window, de-dupe by GUID, return parsed list."""
    from .client import dismiss_cookies
    seen: dict[str, dict] = {}
    for pg in range(1, max_pages + 1):
        url = (f"{base_url}/find/tournament?TournamentFilter.DateFilterType=0"
               f"&page={pg}")
        page.goto(url, wait_until="domcontentloaded")
        dismiss_cookies(page)
        page.wait_for_timeout(700)  # politeness
        found = find_upcoming_tournaments(page.content(), today_iso, horizon_days)
        if not found:
            break
        before = len(seen)
        for t in found:
            seen.setdefault(t["guid"].lower(), t)
        if len(seen) == before:
            break  # no new tournaments this page
    return list(seen.values())
```

- [ ] **Step 2: Build the roster accessor**

In `upcoming_build.py`, add a small helper to get the matching roster (nickname+full_name) for ALL confirmed friends, not just GUID ones:
```python
def _roster_for_matching():  # pragma: no cover
    import csv
    from .config import PLAYERS_CSV
    rows = []
    with open(PLAYERS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            full = (r.get("full_name") or "").strip()
            nick = (r.get("nickname") or "").strip()
            if full:  # need a full name to match on
                rows.append({"nickname": nick, "full_name": full})
    return rows
```

- [ ] **Step 3: Rewrite `run_upcoming` (tournament-first)**

Replace the body of `run_upcoming` with the tournament-first flow:
```python
def run_upcoming(tournament_guids=None, horizon_days=60, max_tournaments=20) -> dict:  # pragma: no cover
    from datetime import datetime
    from playwright.sync_api import sync_playwright

    from .client import dismiss_cookies, ensure_login, new_context
    from .exclude import load_excludes
    from .upcoming_find import fetch_upcoming_tournaments
    from .upcoming_participants import match_friends, parse_participants
    from .upcoming_schedule_parse import parse_player_schedule

    today = datetime.now().astimezone().date().isoformat()
    roster = _roster_for_matching()
    exclude = load_excludes()
    raw = {"tournaments": []}

    with sync_playwright() as p:
        browser, ctx = new_context(p)
        page = ensure_login(ctx)

        tours = fetch_upcoming_tournaments(page, BASE_URL, today, horizon_days)
        for g in (tournament_guids or []):
            if not any(t["guid"].lower() == g.lower() for t in tours):
                tours.append({"name": "", "guid": g, "start_date": None, "end_date": None})
        tours = tours[:max_tournaments]

        for t in tours:
            guid = t["guid"]
            page.goto(f"{BASE_URL}/tournament/{guid}/players", wait_until="domcontentloaded")
            dismiss_cookies(page)
            page.wait_for_timeout(900)  # politeness
            friends = match_friends(parse_participants(page.content()), roster, exclude)
            if not friends:
                continue
            entries = []
            for fr in friends:
                page.goto(f"{BASE_URL}/tournament/{guid}/player/{fr['player_no']}",
                          wait_until="domcontentloaded")
                dismiss_cookies(page)
                page.wait_for_timeout(700)
                cards = page.evaluate(
                    "() => [...document.querySelectorAll('.match')].map(n => n.innerText.trim())"
                )
                nodes = parse_player_schedule(cards, fr["full_name"])
                nodes.sort(key=lambda n: n["time"] or "")
                # group by event into separate timeline entries
                by_ev: dict[str, list] = {}
                for n in nodes:
                    by_ev.setdefault(n["event"], []).append(n)
                for ev, path in by_ev.items():
                    entries.append({"player": fr["nickname"], "player_guid": "",
                                    "event": ev, "path": path})
            if entries:
                raw["tournaments"].append({
                    "name": t["name"], "tournament_guid": guid, "venue": "",
                    "start_date": t["start_date"], "end_date": t["end_date"],
                    "status": "order_published", "entries": entries,
                })
        browser.close()

    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    public = assemble_upcoming(json.loads(json.dumps(raw)), aliases.alias_map(), now_iso)
    private = dict(raw)
    private["generated_at"] = now_iso
    write_outputs(public, private)
    return public
```

> NOTE: the `event` strings here are the raw site labels (e.g. "MD Harraste / Hobby - Group B"). Prettifying them (→ "MD Hobby Grp B") is a display concern; keep raw in the driver and leave any prettify to a pure helper only if a test demands it. YAGNI for now.

- [ ] **Step 4: Update the `__main__.py` flags**

In `src/badminton_tracker/__main__.py`, extend the `upcoming` subparser:
```python
    p_upc.add_argument("--horizon-days", type=int, default=60)
    p_upc.add_argument("--max-tournaments", type=int, default=20)
    p_upc.add_argument("--tournament", action="append", default=[], metavar="GUID")
```
and the dispatch:
```python
    elif args.command == "upcoming":
        from .upcoming_build import run_upcoming
        if args.watch:
            from .upcoming_schedule import watch
            watch(lambda: run_upcoming(args.tournament, args.horizon_days, args.max_tournaments))
        else:
            run_upcoming(args.tournament, args.horizon_days, args.max_tournaments)
```

- [ ] **Step 5: Static check + full unit suite (no live calls)**

Run: `~/.local/bin/uv.exe run ruff check src/ tests/ && ~/.local/bin/uv.exe run pytest -q`
Expected: clean + all pass (the driver isn't unit-tested, but imports must resolve).

- [ ] **Step 6: Commit**

```bash
git add src/badminton_tracker/upcoming_build.py src/badminton_tracker/upcoming_find.py src/badminton_tracker/__main__.py
git commit -m "feat: tournament-first run_upcoming (auto-discover + scoped schedule)"
```

---

## Task 7: Privacy regression test for the new flow

**Files:**
- Modify/extend: the existing privacy guard test (find it: `grep -rl "GUID\|guid" tests/`)
- Test: assert a representative assembled public dict from the NEW raw shape has no GUIDs.

**Interfaces:**
- Consumes: `assemble_upcoming` (existing).

- [ ] **Step 1: Write the failing test**

Add to the privacy test file (e.g. `tests/test_privacy_guard.py`):
```python
def test_assemble_upcoming_strips_tournament_and_player_guids():
    from badminton_tracker.upcoming_build import assemble_upcoming
    raw = {"tournaments": [{
        "name": "T", "tournament_guid": "1A563200-14BA-4328-955A-922A5EEC6374",
        "venue": "", "start_date": "2026-07-04", "end_date": "2026-07-04",
        "status": "order_published",
        "entries": [{"player": "Chau", "player_guid": "d69f71b9-69f2-472e-97b2-4fc80ac43a17",
                     "event": "MD", "path": [{"round": "R1", "opponent": "X", "state": "scheduled"}]}],
    }]}
    pub = assemble_upcoming(raw, {}, "2026-06-28T00:00:00+03:00")
    blob = repr(pub).lower()
    assert "1a563200" not in blob
    assert "d69f71b9" not in blob
```

- [ ] **Step 2: Run, verify pass (assemble_upcoming already strips — this locks it in)**

Run: `~/.local/bin/uv.exe run pytest tests/test_privacy_guard.py -v`
Expected: PASS. If it FAILS, `_strip_guids` regressed — fix `upcoming_build._GUID_KEYS` to include `tournament_guid`/`player_guid` (it already does).

- [ ] **Step 3: Commit**

```bash
git add tests/test_privacy_guard.py
git commit -m "test: lock GUID-stripping for tournament-first upcoming shape"
```

---

## Task 8: HUMAN-run live verification (post-implementation)

> This task is run by the human operator (live site + credentials), not a subagent.

- [ ] **Step 1: Run the real pipeline**

```bash
unset TOURNAMENTSOFTWARE_USERNAME TOURNAMENTSOFTWARE_PASSWORD && \
  PYTHONUTF8=1 PYTHONIOENCODING=utf-8 ~/.local/bin/uv.exe run badminton upcoming --tournament 1A563200-14BA-4328-955A-922A5EEC6374
```

- [ ] **Step 2: Verify Stadin reappears with the friend group**

Expected: `web/upcoming.json` contains the Stadin tournament with entries for Chau (MD + XD), Hien (WD C), Junya (MS B), Maila (WD C), Dao (XD Open), Vu Luu (XD), Thy (WD C) — matching the hand-built file published in PR #3.

- [ ] **Step 3: Privacy gate**

```bash
grep -Eic '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' web/upcoming.json   # must be 0
git ls-files | grep -E 'data/|\.env'   # only .env.example
```

- [ ] **Step 4: Commit the regenerated public file + private state**

```bash
git add web/upcoming.json && git commit -m "data: regenerate upcoming.json via auto-discovery"
git -C data add upcoming_state.json && git -C data commit -m "state: refresh upcoming cache"
```

---

## Self-Review

**Spec coverage:**
- Auto-discover tournaments → Task 3 (parse) + Task 6 (driver). ✓
- GUID-less friend matching by full name → Task 2. ✓
- Scoped-page schedule as primary source → Task 4 + Task 6. ✓
- exclude.csv data file → Task 1. ✓
- Codex P1 (nickname vs full name) → Task 6 (full-name match; nickname only at alias stage). ✓
- Codex P1 (watcher naive/aware) → Task 5. ✓
- Codex P2 (draw cache per event) → addressed by NOT reusing a per-tournament draw cache; the scoped-page flow resolves per friend/event. Draw-projection for unscheduled knockout rounds is deferred (see note below). ✓ (with caveat)
- Codex P2 (round match-groups) → sidestepped; scoped page gives per-match cards. ✓
- Privacy → Task 7 + Global Constraints. ✓
- CLI flags → Task 6 Step 4. ✓
- Bounded/throttled scan → Task 6 (max_tournaments, wait_for_timeout). ✓

**Deferred vs spec (flag for plan-executor):** The spec described draw-projection to fill *unscheduled* knockout rounds and a (tournament,event) draw cache. This plan ships the **pool/order-of-play path** (which covers Stadin and the empty-result bug) and **defers draw-projection for knockout events** to a follow-up, because every tournament observed so far publishes a full order-of-play that makes projection unnecessary. If a knockout tournament with a partial schedule appears, add a task: resolve `(guid,event)` draw via existing `_resolve_event_draw`/`parse_draw`, call `build_path`, append only rounds not already scheduled. This keeps the first delivery small and testable.

**Cache TTL (spec §scan policy):** Also deferred with draw-projection — the first delivery re-fetches every run (bounded by max_tournaments). Add the `fetched_at`/TTL cache as a follow-up task once the core flow is proven live. Noted so it isn't silently dropped.

**Placeholder scan:** No TBD/TODO left. The one simplified body (Task 4 court extraction) has an explicit REFACTOR step + NOTE, not a placeholder.

**Type consistency:** `match_friends` returns `{nickname, full_name, player_no}` (Task 2) — consumed with those exact keys in Task 6. `parse_player_schedule(cards, friend_full_name)` (Task 4) — called with that signature in Task 6. `find_upcoming_tournaments(html, today_iso, horizon_days)` (Task 3) — wrapped by `fetch_upcoming_tournaments` (Task 6 Step 1). Consistent.

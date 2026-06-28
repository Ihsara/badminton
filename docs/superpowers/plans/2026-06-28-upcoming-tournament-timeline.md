# Upcoming-Tournament Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live upcoming-tournament pipeline (scrape draws + order-of-play) and a phone-first vertical-timeline view that shows each tracked friend's projected path to the Final, with player filtering and chat-text export.

**Architecture:** A new pipeline parallel to the historical one. Pure parsers turn saved HTML into structured dicts; a builder assembles a GUID-free `web/upcoming.json` (public) plus a private `data/upcoming_state.json` (holds GUIDs); a self-pacing scheduler decides refresh cadence; a `--watch` loop runs it on the home server. The frontend gains a `#/upcoming` view (vertical timeline + hero + filter + export) and a home-page takeover during active windows.

**Tech Stack:** Python 3.13 via **uv** (never bare pip/python), Playwright (sync API), pytest, ruff. Frontend: vanilla JS (zero-build), no framework.

## Global Constraints

- **uv only** — run everything via `uv run ...`; the agent's shell may lack uv on PATH, then use `~/.local/bin/uv.exe`. Never bare `pip`/`python`.
- **Lint with ruff** — `uv run ruff check` must pass before any task is "done".
- **PRIVACY (rule #4)** — `web/upcoming.json` MUST contain **no profile/tournament GUIDs**. GUIDs live only in `data/upcoming_state.json` (private nested repo, never `git add`ed to the public repo). Before any public push: `git ls-files | grep -E 'data/|\.env'` empty AND `upcoming.json` GUID-free.
- **Two repos** — code/`web/upcoming.json` go to the public repo as Ihsara; anything under `data/` is committed only in the private `data/` repo.
- **Test style** — pytest, `from badminton_tracker.X import Y`, fixture helpers like `tests/test_export_dedup.py`. Parsers tested over **saved HTML fixtures**, no network.
- **Politeness** — scraper uses one reused logged-in session, serial requests with small delays (a prior community scraper was IP-banned).
- **Time zone** — tournament is in Finland; emit ISO-8601 with offset (e.g. `+02:00`/`+03:00`) as scraped; do not convert.
- **File focus** — one responsibility per module, mirroring existing `fetch.py`/`parse.py`/`export.py` separation.

Reference spec: `docs/superpowers/specs/2026-06-28-upcoming-tournament-timeline-design.md`.

## File Structure

**New Python modules** (`src/badminton_tracker/`):
- `upcoming_parse.py` — pure HTML parsers: `find_upcoming_entries`, `parse_draw`, `parse_order_of_play`. No network.
- `upcoming_path.py` — pure path-builder: merge draw + order-of-play into per-friend `path` lists with `done/scheduled/projected` states; round-label normalizer.
- `upcoming_build.py` — orchestrate scrape (Playwright) → build → write `web/upcoming.json` + `data/upcoming_state.json` (atomic).
- `upcoming_schedule.py` — pure `next_refresh_delay(state, now)` + `watch()` loop.
- `upcoming_text.py` — pure `format_chat_text(upcoming, options)` exporter (shared logic mirrored in JS; Python version is the tested spec).

**New config constants** (`src/badminton_tracker/config.py`): `UPCOMING_JSON = web/upcoming.json`, `UPCOMING_STATE_JSON = DATA_DIR / "upcoming_state.json"`.

**CLI** (`src/badminton_tracker/__main__.py`): add `upcoming` subcommand with `--watch`.

**Frontend**:
- `web/app.js` — `viewUpcoming()`, router case, nav-active wiring, load `upcoming.json` in `boot()`, home takeover hook in `viewGroup()`, JS `formatChatText()` + filter/export UI.
- `web/index.html` — add `#nav-upcoming` link.
- `web/styles.css` — timeline/hero/state/filter/export styles.

**Tests** (`tests/`): `test_upcoming_parse.py`, `test_upcoming_path.py`, `test_upcoming_schedule.py`, `test_upcoming_text.py`, plus HTML fixtures in `tests/fixtures/upcoming/`.

**Deployment**: `docker-compose.yml` (or equivalent) — add a second service/command running `badminton upcoming --watch`.

---

## Task 1: Config constants + saved HTML fixtures

**Files:**
- Modify: `src/badminton_tracker/config.py`
- Create: `tests/fixtures/upcoming/draw_knockout.html`
- Create: `tests/fixtures/upcoming/order_of_play.html`
- Create: `tests/fixtures/upcoming/profile_tournaments.html`

**Interfaces:**
- Produces: `UPCOMING_JSON: Path`, `UPCOMING_STATE_JSON: Path` importable from `config`.

This task establishes the test fixtures (real DOM snippets) all parser tasks depend on, and the two path constants. Fixtures are authored from the verified DOM patterns in the spec; capture real HTML from the live site if available during execution (a draw page, a Matches page, a profile /tournaments page), otherwise hand-author minimal-but-faithful snippets containing the exact classes below.

- [ ] **Step 1: Add config constants**

In `src/badminton_tracker/config.py`, after the existing `ALIASES_CSV` block:

```python
# Upcoming-tournament pipeline (parallel to the historical one).
# Public, GUID-free artifact served beside data.json:
UPCOMING_JSON = ROOT / "web" / "upcoming.json"
# Private re-fetch state (holds tournament/profile GUIDs) — lives in data/ repo:
UPCOMING_STATE_JSON = DATA_DIR / "upcoming_state.json"
```

- [ ] **Step 2: Create `tests/fixtures/upcoming/draw_knockout.html`**

Minimal faithful bracket containing the classes `parse_draw` will read. Include at least 3 rounds (Quarter final, Semi final, Final), a Bye, and one inline scheduled timestamp:

```html
<div class="bracket js-bracket">
  <div class="bracket-round">
    <h4 class="bracket-round__title">Quarter final</h4>
    <div class="bracket-round__match-group-wrapper">
      <div class="bracket-round__match-group">
        <div class="match__row has-won"><span class="nav-link__value">Chau</span></div>
        <div class="match__row"><span class="nav-link__value">Real Opponent</span></div>
        <time datetime="2026-03-14T13:30:00+02:00">la 14.3.2026 13.30</time>
      </div>
    </div>
  </div>
  <div class="bracket-round">
    <h4 class="bracket-round__title">Semi final</h4>
    <div class="bracket-round__match-group-wrapper">
      <div class="bracket-round__match-group">
        <div class="match__row"><span class="nav-link__value">Winner</span></div>
        <div class="match__row"><span class="nav-link__value">Bye</span></div>
      </div>
    </div>
  </div>
  <div class="bracket-round">
    <h4 class="bracket-round__title">Final</h4>
    <div class="bracket-round__match-group-wrapper">
      <div class="bracket-round__match-group"></div>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Create `tests/fixtures/upcoming/order_of_play.html`**

A Matches page day with two time-grouped matches, one with a court tooltip:

```html
<div class="tournament-matches" data-date="2026-03-14">
  <div class="match-group">
    <h5 class="match-group__header">9.30</h5>
    <div class="match-group__item">
      <div class="match match--list">
        <div class="match__header-title">MS B Quarter final</div>
        <div class="match__header-aside" title="Duration: 31m | Valkeavuoren liikuntahalli - K2 Mailapelikauppa"></div>
        <div class="match__row has-won"><span class="nav-link__value">Chau</span></div>
        <div class="match__row"><span class="nav-link__value">Real Opponent</span></div>
      </div>
    </div>
  </div>
  <div class="match-group">
    <h5 class="match-group__header">13.30</h5>
    <div class="match-group__item">
      <div class="match match--list">
        <div class="match__header-title">WD B Round 1</div>
        <div class="match__header-aside" title="Duration: | Valkeavuoren liikuntahalli - K5"></div>
        <div class="match__row"><span class="nav-link__value">Vu Luu</span></div>
        <div class="match__row"><span class="nav-link__value">Some Pair</span></div>
      </div>
    </div>
  </div>
</div>
```

- [ ] **Step 4: Create `tests/fixtures/upcoming/profile_tournaments.html`**

A profile `/tournaments` card with one FUTURE-dated entry (so `find_upcoming_entries` can pick it out). Reuse the existing `.module--card` / `.media__title` / `Luokka:` / `.match` shape from `parse.py`'s `_EXTRACT_JS`:

```html
<div class="module--card">
  <a class="media__title" href="/tournament/AAAA1111-2222-3333-4444-555566667777">Stadin Mestaruuskilpailut</a>
  <div class="module__footer">14.3.2026 - 15.3.2026</div>
  <h4>Luokka: MS B</h4>
  <div class="match">
    <div class="match__header-title">Quarter final</div>
    <div class="match__body">
      <div class="match__row"><div class="match__row-title-value"><span class="nav-link__value">Chau</span></div></div>
      <div class="match__row"><div class="match__row-title-value"><span class="nav-link__value">Real Opponent</span></div></div>
    </div>
  </div>
</div>
```

- [ ] **Step 5: Verify constants import**

Run: `~/.local/bin/uv.exe run python -c "from badminton_tracker.config import UPCOMING_JSON, UPCOMING_STATE_JSON; print(UPCOMING_JSON, UPCOMING_STATE_JSON)"`
Expected: prints both paths, no error.

- [ ] **Step 6: Commit**

```bash
git add src/badminton_tracker/config.py tests/fixtures/upcoming/
git commit -m "Add upcoming pipeline config paths + HTML test fixtures"
```

---

## Task 2: `parse_draw` — bracket → rounds

**Files:**
- Create: `src/badminton_tracker/upcoming_parse.py`
- Create: `tests/test_upcoming_parse.py`
- Test fixture: `tests/fixtures/upcoming/draw_knockout.html`

**Interfaces:**
- Produces: `parse_draw(html: str) -> list[dict]`. Each round dict:
  `{"round_label": str, "slots": list[str], "scheduled_iso": str | None}`.
  `slots` are the displayed player/team names in that round's first/displayed
  match-group (length 0–2; "Bye" kept verbatim). `round_label` is the raw header
  text ("Quarter final"). Parses HTML with the stdlib `html.parser` (no new deps).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_upcoming_parse.py
from __future__ import annotations

from pathlib import Path

from badminton_tracker.upcoming_parse import parse_draw

FIX = Path(__file__).parent / "fixtures" / "upcoming"


def _read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_parse_draw_returns_round_labels_in_order():
    rounds = parse_draw(_read("draw_knockout.html"))
    assert [r["round_label"] for r in rounds] == ["Quarter final", "Semi final", "Final"]


def test_parse_draw_extracts_slot_names():
    rounds = parse_draw(_read("draw_knockout.html"))
    qf = rounds[0]
    assert qf["slots"] == ["Chau", "Real Opponent"]


def test_parse_draw_keeps_bye_verbatim():
    rounds = parse_draw(_read("draw_knockout.html"))
    sf = rounds[1]
    assert "Bye" in sf["slots"]


def test_parse_draw_reads_inline_scheduled_iso():
    rounds = parse_draw(_read("draw_knockout.html"))
    assert rounds[0]["scheduled_iso"] == "2026-03-14T13:30:00+02:00"


def test_parse_draw_final_with_no_players_has_empty_slots():
    rounds = parse_draw(_read("draw_knockout.html"))
    assert rounds[2]["slots"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'badminton_tracker.upcoming_parse'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/badminton_tracker/upcoming_parse.py
"""Pure HTML parsers for the upcoming-tournament pipeline.

No network: every function takes raw HTML and returns plain dicts/lists, so they
are unit-tested against saved fixtures. Mirrors the extraction style of parse.py
but uses the stdlib HTMLParser instead of Playwright page.evaluate, since these
run in the build step over already-fetched HTML.
"""

from __future__ import annotations

from html.parser import HTMLParser


class _DrawParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rounds: list[dict] = []
        self._cur: dict | None = None
        self._capture: str | None = None  # 'title' | 'value' | 'time'
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        cls = (a.get("class") or "")
        if "bracket-round__title" in cls:
            self._capture, self._buf = "title", []
        elif "nav-link__value" in cls and self._cur is not None:
            self._capture, self._buf = "value", []
        elif tag == "time" and self._cur is not None:
            dt = a.get("datetime")
            if dt and self._cur.get("scheduled_iso") is None:
                self._cur["scheduled_iso"] = dt

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture == "title":
            label = "".join(self._buf).strip()
            self._cur = {"round_label": label, "slots": [], "scheduled_iso": None}
            self.rounds.append(self._cur)
        elif self._capture == "value" and self._cur is not None:
            val = "".join(self._buf).strip()
            if val:
                self._cur["slots"].append(val)
        if self._capture in ("title", "value"):
            self._capture = None


def parse_draw(html: str) -> list[dict]:
    p = _DrawParser()
    p.feed(html)
    return p.rounds
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_parse.py -v`
Expected: 5 PASS. If the `Final` round captures stray slots, confirm the fixture's Final match-group is empty.

- [ ] **Step 5: Lint**

Run: `~/.local/bin/uv.exe run ruff check src/badminton_tracker/upcoming_parse.py tests/test_upcoming_parse.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/badminton_tracker/upcoming_parse.py tests/test_upcoming_parse.py
git commit -m "Add parse_draw: bracket HTML -> ordered rounds with slots + scheduled time"
```

---

## Task 3: `parse_order_of_play` — Matches page → timed/courted matches

**Files:**
- Modify: `src/badminton_tracker/upcoming_parse.py`
- Modify: `tests/test_upcoming_parse.py`
- Test fixture: `tests/fixtures/upcoming/order_of_play.html`

**Interfaces:**
- Consumes: nothing from prior tasks.
- Produces: `parse_order_of_play(html: str, date_iso: str) -> list[dict]`. Each:
  `{"time": "HH.MM", "court": str | None, "event": str, "round_label": str,
  "players": list[str]}`. `date_iso` is the day the page represents ("2026-03-14"),
  used by later tasks to compose a full timestamp. Court is parsed from the
  `match__header-aside` `title` attribute (text after the last `- ` / `K\d+`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_upcoming_parse.py`:

```python
from badminton_tracker.upcoming_parse import parse_order_of_play


def test_order_of_play_groups_by_time():
    rows = parse_order_of_play(_read("order_of_play.html"), "2026-03-14")
    assert [r["time"] for r in rows] == ["9.30", "13.30"]


def test_order_of_play_extracts_court():
    rows = parse_order_of_play(_read("order_of_play.html"), "2026-03-14")
    assert rows[0]["court"] == "K2"
    assert rows[1]["court"] == "K5"


def test_order_of_play_splits_event_and_round():
    rows = parse_order_of_play(_read("order_of_play.html"), "2026-03-14")
    assert rows[0]["event"] == "MS B"
    assert rows[0]["round_label"] == "Quarter final"


def test_order_of_play_lists_players():
    rows = parse_order_of_play(_read("order_of_play.html"), "2026-03-14")
    assert rows[0]["players"] == ["Chau", "Real Opponent"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_parse.py -k order_of_play -v`
Expected: FAIL — `ImportError: cannot import name 'parse_order_of_play'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/badminton_tracker/upcoming_parse.py`:

```python
import re

_COURT_RE = re.compile(r"(K\d+|Court\s*\d+)", re.IGNORECASE)
# Known event codes appear at the head of the match title ("MS B Quarter final").
_EVENT_HEAD_RE = re.compile(
    r"^((?:MS|WS|MD|WD|XD|MK|NK|MN|NN|SN)\b(?:\s+\S+)?)\s+(.*)$"
)


def _court_from_title(title: str | None) -> str | None:
    if not title:
        return None
    m = _COURT_RE.search(title)
    return m.group(1).replace("Court ", "K").replace("Court", "K") if m else None


def _split_title(text: str) -> tuple[str, str]:
    """'MS B Quarter final' -> ('MS B', 'Quarter final')."""
    m = _EVENT_HEAD_RE.match(text.strip())
    return (m.group(1).strip(), m.group(2).strip()) if m else ("", text.strip())


class _OrderParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict] = []
        self._time: str | None = None
        self._cur: dict | None = None
        self._capture: str | None = None  # 'time' | 'title' | 'value'
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        cls = a.get("class") or ""
        if "match-group__header" in cls:
            self._capture, self._buf = "time", []
        elif "match--list" in cls:
            self._cur = {"time": self._time, "court": None, "event": "",
                         "round_label": "", "players": []}
            self.rows.append(self._cur)
        elif "match__header-title" in cls and self._cur is not None:
            self._capture, self._buf = "title", []
        elif "match__header-aside" in cls and self._cur is not None:
            self._cur["court"] = _court_from_title(a.get("title"))
        elif "nav-link__value" in cls and self._cur is not None:
            self._capture, self._buf = "value", []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        text = "".join(self._buf).strip()
        if self._capture == "time":
            self._time = text
        elif self._capture == "title" and self._cur is not None:
            self._cur["event"], self._cur["round_label"] = _split_title(text)
        elif self._capture == "value" and self._cur is not None and text:
            self._cur["players"].append(text)
        self._capture = None


def parse_order_of_play(html: str, date_iso: str) -> list[dict]:
    p = _OrderParser()
    p.feed(html)
    for r in p.rows:
        r["date"] = date_iso
    return p.rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_parse.py -v`
Expected: all (Task 2 + Task 3) PASS.

- [ ] **Step 5: Lint**

Run: `~/.local/bin/uv.exe run ruff check src/badminton_tracker/upcoming_parse.py tests/test_upcoming_parse.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/badminton_tracker/upcoming_parse.py tests/test_upcoming_parse.py
git commit -m "Add parse_order_of_play: Matches page -> timed/courted match rows"
```

---

## Task 4: `find_upcoming_entries` — profile page → future entries

**Files:**
- Modify: `src/badminton_tracker/upcoming_parse.py`
- Modify: `tests/test_upcoming_parse.py`
- Test fixture: `tests/fixtures/upcoming/profile_tournaments.html`

**Interfaces:**
- Produces: `find_upcoming_entries(html: str, today_iso: str) -> list[dict]`.
  Each: `{"tournament": str, "tournament_guid": str | None, "event": str,
  "start_date": str | None, "end_date": str | None}` — only cards whose
  `end_date >= today_iso` (or whose dates are unparseable but contain a future
  year are kept). Dates parsed from the Finnish `d.m.yyyy - d.m.yyyy` footer to ISO.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_upcoming_parse.py`:

```python
from badminton_tracker.upcoming_parse import find_upcoming_entries


def test_find_upcoming_entries_keeps_future_card():
    out = find_upcoming_entries(_read("profile_tournaments.html"), "2026-01-01")
    assert len(out) == 1
    e = out[0]
    assert e["tournament"] == "Stadin Mestaruuskilpailut"
    assert e["event"] == "MS B"


def test_find_upcoming_entries_parses_dates_to_iso():
    out = find_upcoming_entries(_read("profile_tournaments.html"), "2026-01-01")
    assert out[0]["start_date"] == "2026-03-14"
    assert out[0]["end_date"] == "2026-03-15"


def test_find_upcoming_entries_extracts_guid_from_href():
    out = find_upcoming_entries(_read("profile_tournaments.html"), "2026-01-01")
    assert out[0]["tournament_guid"] == "AAAA1111-2222-3333-4444-555566667777"


def test_find_upcoming_entries_drops_past_card():
    out = find_upcoming_entries(_read("profile_tournaments.html"), "2027-01-01")
    assert out == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_parse.py -k upcoming_entries -v`
Expected: FAIL — `ImportError: cannot import name 'find_upcoming_entries'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/badminton_tracker/upcoming_parse.py`:

```python
_GUID_RE = re.compile(r"/tournament/([0-9A-Fa-f-]{36})")
_DATE_RANGE_RE = re.compile(
    r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s*-\s*(\d{1,2})\.(\d{1,2})\.(\d{4})"
)
_SINGLE_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def _iso(d: str, m: str, y: str) -> str:
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def _parse_dates(footer: str) -> tuple[str | None, str | None]:
    m = _DATE_RANGE_RE.search(footer)
    if m:
        return _iso(m.group(1), m.group(2), m.group(3)), _iso(m.group(4), m.group(5), m.group(6))
    s = _SINGLE_DATE_RE.search(footer)
    if s:
        iso = _iso(s.group(1), s.group(2), s.group(3))
        return iso, iso
    return None, None


class _EntriesParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.cards: list[dict] = []
        self._cur: dict | None = None
        self._capture: str | None = None  # 'title' | 'footer' | 'luokka'
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        cls = a.get("class") or ""
        if "module--card" in cls:
            self._cur = {"tournament": "", "tournament_guid": None, "event": "",
                         "start_date": None, "end_date": None}
            self.cards.append(self._cur)
        elif "media__title" in cls and self._cur is not None:
            href = a.get("href") or ""
            m = _GUID_RE.search(href)
            if m:
                self._cur["tournament_guid"] = m.group(1)
            self._capture, self._buf = "title", []
        elif "module__footer" in cls and self._cur is not None:
            self._capture, self._buf = "footer", []
        elif tag == "h4" and self._cur is not None:
            self._capture, self._buf = "luokka", []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        text = "".join(self._buf).strip()
        if self._capture == "title" and self._cur is not None:
            self._cur["tournament"] = text
        elif self._capture == "footer" and self._cur is not None:
            self._cur["start_date"], self._cur["end_date"] = _parse_dates(text)
        elif self._capture == "luokka" and self._cur is not None:
            if text.lower().startswith("luokka") and not self._cur["event"]:
                self._cur["event"] = text.split(":", 1)[-1].strip()
        self._capture = None


def find_upcoming_entries(html: str, today_iso: str) -> list[dict]:
    p = _EntriesParser()
    p.feed(html)
    out = []
    for c in p.cards:
        end = c["end_date"]
        if end is None or end >= today_iso:
            out.append(c)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_parse.py -v`
Expected: all parser tests PASS.

- [ ] **Step 5: Lint**

Run: `~/.local/bin/uv.exe run ruff check src/badminton_tracker/upcoming_parse.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/badminton_tracker/upcoming_parse.py tests/test_upcoming_parse.py
git commit -m "Add find_upcoming_entries: profile page -> future-dated entries"
```

---

## Task 5: `upcoming_path` — round normalizer + path builder

**Files:**
- Create: `src/badminton_tracker/upcoming_path.py`
- Create: `tests/test_upcoming_path.py`

**Interfaces:**
- Consumes: `parse_draw` output (rounds), `parse_order_of_play` output (timed rows).
- Produces:
  - `normalize_round(label: str) -> str` → one of `"R128","R64","R32","R16","QF","SF","Final"` (maps "Quarter final"→"QF", "Kierros 16"→"R16", "Round 1"→"R1" fallback, etc.).
  - `build_path(rounds: list[dict], schedule: list[dict], friend: str, event: str, today_iso: str) -> list[dict]` → ordered path nodes:
    `{"round": str, "state": "done"|"scheduled"|"projected", "opponent": str|None,
    "result": str|None, "court": str|None, "time": str|None, "time_kind":
    "exact"|"not_before"|None, "day": str|None, "session": str|None}`.
    State rules: a node is `done` if the schedule row for that round has a result/`has_won` (encoded as `result` present); `scheduled` if it has a real opponent + time but no result; `projected` otherwise (opponent shown as `"Winner of <prevRound>"` or None for the round after the friend's last known slot).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_upcoming_path.py
from __future__ import annotations

from badminton_tracker.upcoming_path import build_path, normalize_round


def test_normalize_round_maps_named_rounds():
    assert normalize_round("Quarter final") == "QF"
    assert normalize_round("Semi final") == "SF"
    assert normalize_round("Final") == "Final"


def test_normalize_round_maps_finnish_and_numeric():
    assert normalize_round("Kierros 16") == "R16"
    assert normalize_round("Round of 32") == "R32"


def test_build_path_marks_scheduled_node():
    rounds = [
        {"round_label": "Quarter final", "slots": ["Chau", "Real Opponent"],
         "scheduled_iso": "2026-03-14T13:30:00+02:00"},
        {"round_label": "Semi final", "slots": ["Winner", "Bye"], "scheduled_iso": None},
        {"round_label": "Final", "slots": [], "scheduled_iso": None},
    ]
    schedule = [
        {"event": "MS B", "round_label": "Quarter final", "time": "13.30",
         "court": "K3", "players": ["Chau", "Real Opponent"], "date": "2026-03-14",
         "result": None},
    ]
    path = build_path(rounds, schedule, "Chau", "MS B", "2026-03-14")
    qf = next(n for n in path if n["round"] == "QF")
    assert qf["state"] == "scheduled"
    assert qf["opponent"] == "Real Opponent"
    assert qf["court"] == "K3"


def test_build_path_marks_done_node_with_result():
    rounds = [{"round_label": "Quarter final", "slots": ["Chau", "Beaten Foe"],
               "scheduled_iso": "2026-03-14T09:30:00+02:00"}]
    schedule = [{"event": "MS B", "round_label": "Quarter final", "time": "9.30",
                 "court": "K2", "players": ["Chau", "Beaten Foe"],
                 "date": "2026-03-14", "result": "W 21-15 21-12"}]
    path = build_path(rounds, schedule, "Chau", "MS B", "2026-03-14")
    assert path[0]["state"] == "done"
    assert path[0]["result"] == "W 21-15 21-12"


def test_build_path_projects_future_round_with_generic_opponent():
    rounds = [
        {"round_label": "Quarter final", "slots": ["Chau", "Real Opponent"],
         "scheduled_iso": "2026-03-14T13:30:00+02:00"},
        {"round_label": "Semi final", "slots": [], "scheduled_iso": None},
    ]
    schedule = [{"event": "MS B", "round_label": "Quarter final", "time": "13.30",
                 "court": "K3", "players": ["Chau", "Real Opponent"],
                 "date": "2026-03-14", "result": None}]
    path = build_path(rounds, schedule, "Chau", "MS B", "2026-03-14")
    sf = next(n for n in path if n["round"] == "SF")
    assert sf["state"] == "projected"
    assert sf["opponent"] in (None, "Winner of QF")
    assert sf["time"] is None  # never a precise time for projected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_path.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# src/badminton_tracker/upcoming_path.py
"""Merge a draw bracket and the order-of-play into one friend's projected path.

Pure functions over the dicts produced by upcoming_parse — no network. The path
is the spine of the timeline UI: one node per round from the friend's current
position up to the Final, each tagged done/scheduled/projected so the frontend
can render decaying confidence honestly (no invented names or precise times).
"""

from __future__ import annotations

import re

_NAMED = {
    "final": "Final",
    "semi final": "SF", "semifinal": "SF", "semfinal": "SF",
    "quarter final": "QF", "quarterfinal": "QF",
}
_NUM_RE = re.compile(r"(\d+)")


def normalize_round(label: str) -> str:
    s = (label or "").strip().lower()
    if s in _NAMED:
        return _NAMED[s]
    if s.startswith(("kierros", "round")):
        m = _NUM_RE.search(s)
        if m:
            n = m.group(1)
            # "Round of 32" / "Kierros 32" -> R32
            return f"R{n}"
    m = _NUM_RE.search(s)
    return f"R{m.group(1)}" if m else (label or "").strip()


def _name_matches(friend: str, names: list[str]) -> bool:
    f = friend.strip().lower()
    return any(f == n.strip().lower() for n in names)


def _opponent(friend: str, names: list[str]) -> str | None:
    f = friend.strip().lower()
    others = [n for n in names if n.strip().lower() != f and n.strip().lower() != "bye"]
    return others[0] if others else None


def build_path(rounds: list[dict], schedule: list[dict], friend: str,
               event: str, today_iso: str) -> list[dict]:
    # Index schedule rows by normalized round for this event.
    sched_by_round: dict[str, dict] = {}
    for row in schedule:
        if row.get("event") and row["event"] != event:
            continue
        if not _name_matches(friend, row.get("players", [])):
            continue
        sched_by_round[normalize_round(row["round_label"])] = row

    path: list[dict] = []
    prev_round: str | None = None
    friend_seen = False
    for r in rounds:
        rnd = normalize_round(r["round_label"])
        srow = sched_by_round.get(rnd)
        slot_has_friend = _name_matches(friend, r.get("slots", []))
        if slot_has_friend:
            friend_seen = True

        node = {"round": rnd, "state": "projected", "opponent": None,
                "result": None, "court": None, "time": None,
                "time_kind": None, "day": None, "session": None}

        if srow and srow.get("result"):
            node["state"] = "done"
            node["result"] = srow["result"]
            node["opponent"] = _opponent(friend, srow.get("players", []))
            node["court"] = srow.get("court")
            node["time"] = _compose_time(srow)
            node["time_kind"] = "exact"
        elif srow:
            node["state"] = "scheduled"
            node["opponent"] = _opponent(friend, srow.get("players", []))
            node["court"] = srow.get("court")
            node["time"] = _compose_time(srow)
            node["time_kind"] = srow.get("time_kind") or "exact"
        elif slot_has_friend and r.get("scheduled_iso"):
            node["state"] = "scheduled"
            node["opponent"] = _opponent(friend, r.get("slots", []))
            node["time"] = r["scheduled_iso"]
            node["time_kind"] = "exact"
        else:
            # No concrete info: projected. Name opponent generically only if the
            # friend has already entered the bracket (so this round really is theirs).
            node["state"] = "projected"
            node["opponent"] = f"Winner of {prev_round}" if (friend_seen and prev_round) else None
            node["day"] = r.get("scheduled_iso", None) and r["scheduled_iso"][:10]

        path.append(node)
        prev_round = rnd
    return path


def _compose_time(srow: dict) -> str | None:
    """Combine the day ('2026-03-14') and 'HH.MM' clock into an ISO string."""
    t = srow.get("time")
    d = srow.get("date")
    if not t or not d:
        return None
    hh, _, mm = t.replace(".", ":").partition(":")
    try:
        return f"{d}T{int(hh):02d}:{int(mm or 0):02d}:00"
    except ValueError:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_path.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint**

Run: `~/.local/bin/uv.exe run ruff check src/badminton_tracker/upcoming_path.py tests/test_upcoming_path.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/badminton_tracker/upcoming_path.py tests/test_upcoming_path.py
git commit -m "Add upcoming_path: round normalizer + done/scheduled/projected path builder"
```

---

## Task 6: `next_refresh_delay` — self-pacing scheduler

**Files:**
- Create: `src/badminton_tracker/upcoming_schedule.py`
- Create: `tests/test_upcoming_schedule.py`

**Interfaces:**
- Produces: `next_refresh_delay(state: dict, now: datetime) -> int` (seconds).
  `state` = the `upcoming.json`-shaped dict (has `tournaments` with `start_date`,
  `end_date`, `status`, and `entries[].path[].time`). `now` is timezone-aware.
  Bands (from spec): no tournament within 7 days → 86400; ≤3 days away & not
  order-published → 21600; order-published & today is a match day → 1800;
  friend match within 2h → 900; finished/past → 86400.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_upcoming_schedule.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from badminton_tracker.upcoming_schedule import next_refresh_delay

TZ = timezone(timedelta(hours=2))


def _state(**tour):
    base = {"start_date": "2026-03-14", "end_date": "2026-03-15",
            "status": "entries", "entries": []}
    base.update(tour)
    return {"tournaments": [base]}


def test_no_upcoming_tournament_polls_daily():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=TZ)
    assert next_refresh_delay(_state(), now) == 86400


def test_near_tournament_no_draw_polls_6h():
    now = datetime(2026, 3, 12, 12, 0, tzinfo=TZ)  # 2 days before start
    assert next_refresh_delay(_state(status="entries"), now) == 21600


def test_match_day_order_published_polls_30m():
    now = datetime(2026, 3, 14, 8, 0, tzinfo=TZ)  # on start day
    assert next_refresh_delay(_state(status="order_published"), now) == 1800


def test_friend_match_within_2h_polls_15m():
    now = datetime(2026, 3, 14, 12, 0, tzinfo=TZ)
    st = _state(status="order_published",
                entries=[{"player": "Chau", "event": "MS B",
                          "path": [{"round": "QF", "state": "scheduled",
                                    "time": "2026-03-14T13:30:00+02:00"}]}])
    assert next_refresh_delay(st, now) == 900


def test_finished_tournament_polls_daily():
    now = datetime(2026, 3, 20, 12, 0, tzinfo=TZ)  # after end_date
    assert next_refresh_delay(_state(status="order_published"), now) == 86400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_schedule.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# src/badminton_tracker/upcoming_schedule.py
"""Self-pacing refresh cadence for the upcoming pipeline + the --watch loop.

next_refresh_delay is pure (testable); watch() is the thin loop the home server
runs. The scraper polls hard only when a tracked friend's match is imminent and
backs off to daily otherwise, so it stays polite to tournamentsoftware.com.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta

DAILY = 86400
SIX_HOURS = 21600
THIRTY_MIN = 1800
FIFTEEN_MIN = 900


def _d(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def _dt(s: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


def next_refresh_delay(state: dict, now: datetime) -> int:
    today = now.date()
    best = DAILY
    for t in state.get("tournaments", []):
        start, end = _d(t.get("start_date")), _d(t.get("end_date"))
        if end and today > end:
            continue  # finished -> leave at daily
        # Imminent friend match?
        for e in t.get("entries", []):
            for node in e.get("path", []):
                if node.get("state") != "scheduled":
                    continue
                mt = _dt(node.get("time"))
                if mt and timedelta(0) <= (mt - now) <= timedelta(hours=2):
                    return FIFTEEN_MIN
        # Match day with order published?
        if (t.get("status") == "order_published" and start and end
                and start <= today <= end):
            best = min(best, THIRTY_MIN)
            continue
        # Near tournament, draw not yet published?
        if start and timedelta(0) <= (start - today) <= timedelta(days=3):
            best = min(best, SIX_HOURS)
    return best


def watch(run_once) -> None:  # pragma: no cover - thin loop
    """Repeatedly run `run_once()` (which returns the freshly-built state dict),
    then sleep until the computed next refresh."""
    while True:
        state = run_once()
        delay = next_refresh_delay(state or {}, datetime.now().astimezone())
        time.sleep(delay)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_schedule.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint**

Run: `~/.local/bin/uv.exe run ruff check src/badminton_tracker/upcoming_schedule.py tests/test_upcoming_schedule.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/badminton_tracker/upcoming_schedule.py tests/test_upcoming_schedule.py
git commit -m "Add next_refresh_delay self-pacing scheduler + watch loop"
```

---

## Task 7: `format_chat_text` — Python exporter (the tested spec)

**Files:**
- Create: `src/badminton_tracker/upcoming_text.py`
- Create: `tests/test_upcoming_text.py`

**Interfaces:**
- Produces: `format_chat_text(upcoming: dict, options: dict) -> str`.
  `options` keys: `players: list[str] | None` (filter; None = all),
  `tournaments: list[str] | None`, `horizon: "next" | "full"` (next match only
  vs whole path), `fields: set[str]` ⊆ `{"court","opponent","venue_time","projected"}`.
  Output: chat-friendly multi-line text (see spec example). This Python version is
  the canonical, unit-tested spec; the JS `formatChatText` in Task 9 mirrors it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_upcoming_text.py
from __future__ import annotations

from badminton_tracker.upcoming_text import format_chat_text

UPCOMING = {
    "tournaments": [{
        "name": "Stadin", "start_date": "2026-03-14", "end_date": "2026-03-15",
        "entries": [
            {"player": "Chau", "event": "MS B", "path": [
                {"round": "QF", "state": "scheduled", "opponent": "Real Opponent",
                 "court": "K3", "time": "2026-03-14T13:30:00+02:00", "time_kind": "not_before"},
                {"round": "SF", "state": "projected", "opponent": "Winner of QF",
                 "day": "2026-03-15", "session": "afternoon"},
            ]},
            {"player": "Vu Luu", "event": "WD B", "path": [
                {"round": "R32", "state": "scheduled", "opponent": "Some Pair",
                 "court": "K5", "time": "2026-03-14T10:15:00+02:00", "time_kind": "exact"},
            ]},
        ],
    }]
}


def test_includes_tournament_header():
    out = format_chat_text(UPCOMING, {"horizon": "next", "fields": {"court", "opponent"}})
    assert "Stadin" in out


def test_filters_to_selected_players():
    out = format_chat_text(UPCOMING, {"players": ["Chau"], "horizon": "next",
                                      "fields": {"court", "opponent"}})
    assert "Chau" in out
    assert "Vu Luu" not in out


def test_horizon_next_shows_only_first_unplayed_round():
    out = format_chat_text(UPCOMING, {"players": ["Chau"], "horizon": "next",
                                      "fields": {"court", "opponent"}})
    assert "QF" in out
    assert "SF" not in out  # next-only hides projected rounds


def test_horizon_full_shows_projected_when_requested():
    out = format_chat_text(UPCOMING, {"players": ["Chau"], "horizon": "full",
                                      "fields": {"court", "opponent", "projected"}})
    assert "SF" in out


def test_not_before_time_rendered_with_tilde():
    out = format_chat_text(UPCOMING, {"players": ["Chau"], "horizon": "next",
                                      "fields": {"court", "opponent"}})
    assert "~13:30" in out


def test_court_field_toggle_off_hides_court():
    out = format_chat_text(UPCOMING, {"players": ["Vu Luu"], "horizon": "next",
                                      "fields": {"opponent"}})
    assert "K5" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_text.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# src/badminton_tracker/upcoming_text.py
"""Chat-friendly plaintext export of the upcoming timeline.

Pure function so it can be unit-tested as the canonical spec; the frontend's
formatChatText (app.js) mirrors this output. Honors the user's chosen filters
(players, tournaments) and options (horizon, fields).
"""

from __future__ import annotations


def _clock(iso: str | None, not_before: bool) -> str:
    if not iso:
        return ""
    hhmm = iso[11:16] if len(iso) >= 16 else ""
    return ("~" + hhmm) if (not_before and hhmm) else hhmm


def _line(player: str, event: str, node: dict, fields: set[str]) -> str:
    parts = [f"{player} ({event}): {node['round']}"]
    if node["state"] in ("scheduled", "done"):
        clk = _clock(node.get("time"), node.get("time_kind") == "not_before")
        if clk:
            parts.append(clk)
        if "court" in fields and node.get("court"):
            parts.append(f"Court {node['court']}")
        if "opponent" in fields and node.get("opponent"):
            parts.append(f"vs {node['opponent']}")
    else:  # projected
        when = node.get("session") or node.get("day") or ""
        opp = node.get("opponent") or "TBD"
        parts.append(f"{opp} ({when})".strip())
    return " ".join(parts)


def _first_relevant(path: list[dict], horizon: str) -> list[dict]:
    upcoming = [n for n in path if n["state"] in ("scheduled", "projected")]
    if horizon == "next":
        for n in upcoming:
            if n["state"] == "scheduled":
                return [n]
        return upcoming[:1]
    return upcoming


def format_chat_text(upcoming: dict, options: dict) -> str:
    players = options.get("players")
    tours = options.get("tournaments")
    horizon = options.get("horizon", "next")
    fields = set(options.get("fields") or {"court", "opponent"})
    show_projected = "projected" in fields or horizon == "full"

    out: list[str] = []
    for t in upcoming.get("tournaments", []):
        if tours and t["name"] not in tours:
            continue
        lines: list[str] = []
        for e in t.get("entries", []):
            if players and e["player"] not in players:
                continue
            nodes = _first_relevant(e["path"], horizon)
            for n in nodes:
                if n["state"] == "projected" and not show_projected:
                    continue
                lines.append(_line(e["player"], e["event"], n, fields))
        if lines:
            out.append(f"🏸 {t['name']}")
            out.extend(lines)
    return "\n".join(out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_text.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint**

Run: `~/.local/bin/uv.exe run ruff check src/badminton_tracker/upcoming_text.py tests/test_upcoming_text.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/badminton_tracker/upcoming_text.py tests/test_upcoming_text.py
git commit -m "Add format_chat_text exporter with player/tournament/horizon/field options"
```

---

## Task 8: `upcoming_build` — orchestrate scrape → JSON (Playwright)

**Files:**
- Create: `src/badminton_tracker/upcoming_build.py`
- Modify: `src/badminton_tracker/__main__.py`
- Create: `tests/test_upcoming_build.py`

**Interfaces:**
- Consumes: `find_upcoming_entries`, `parse_draw`, `parse_order_of_play`,
  `build_path`, `aliases.alias_map`/`aliases.apply`, `fetch.load_players`,
  `client.ensure_login`/`new_context`, `config.UPCOMING_JSON`/`UPCOMING_STATE_JSON`.
- Produces:
  - `assemble_upcoming(raw: dict, alias_map: dict, now_iso: str) -> dict` — **pure**:
    takes already-scraped per-friend raw data and produces the public
    `upcoming.json` dict (aliases applied to friend names; **GUIDs stripped**).
  - `write_outputs(public: dict, private: dict) -> None` — atomic writes (temp +
    rename) to `UPCOMING_JSON` and `UPCOMING_STATE_JSON`.
  - `run_upcoming() -> dict` — full Playwright scrape+build+write; returns the
    public dict (used by `watch`).

Only `assemble_upcoming` is unit-tested (pure); the Playwright `run_upcoming` is
exercised manually in Task 12. This keeps network code thin.

- [ ] **Step 1: Write the failing test (pure assembler only)**

```python
# tests/test_upcoming_build.py
from __future__ import annotations

from badminton_tracker.upcoming_build import assemble_upcoming


def test_assemble_strips_guids_and_applies_aliases():
    raw = {
        "tournaments": [{
            "name": "Stadin", "tournament_guid": "AAAA1111-2222-3333-4444-555566667777",
            "venue": "Hall", "start_date": "2026-03-14", "end_date": "2026-03-15",
            "status": "order_published",
            "entries": [{
                "player": "Chau's Partner", "player_guid": "BBBB...",
                "event": "WD B",
                "path": [{"round": "R32", "state": "scheduled", "opponent": "Some Pair",
                          "court": "K5", "time": "2026-03-14T10:15:00+02:00",
                          "time_kind": "exact"}],
            }],
        }]
    }
    alias_map = {"Chau's Partner": "Bonnie"}
    out = assemble_upcoming(raw, alias_map, "2026-03-13T20:00:00+02:00")

    blob = repr(out)
    assert "AAAA1111" not in blob  # tournament guid stripped
    assert "player_guid" not in blob  # player guid stripped
    assert out["tournaments"][0]["entries"][0]["player"] == "Bonnie"  # alias applied
    assert out["generated_at"] == "2026-03-13T20:00:00+02:00"


def test_assemble_keeps_opponent_names_verbatim():
    raw = {"tournaments": [{"name": "T", "tournament_guid": "G", "venue": "",
            "start_date": "2026-03-14", "end_date": "2026-03-14",
            "status": "order_published",
            "entries": [{"player": "Chau", "player_guid": "X", "event": "MS B",
                "path": [{"round": "QF", "state": "scheduled", "opponent": "Real Opponent",
                          "court": "K1", "time": None, "time_kind": None}]}]}]}
    out = assemble_upcoming(raw, {}, "2026-03-13T20:00:00+02:00")
    assert out["tournaments"][0]["entries"][0]["path"][0]["opponent"] == "Real Opponent"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_build.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```python
# src/badminton_tracker/upcoming_build.py
"""Scrape upcoming draws + order-of-play, build the public timeline JSON.

Split into a PURE assembler (assemble_upcoming — unit-tested, strips GUIDs,
applies aliases) and a thin Playwright driver (run_upcoming). Outputs:
  web/upcoming.json        — public, GUID-FREE (rule #4)
  data/upcoming_state.json — private, keeps GUIDs for re-fetch
"""

from __future__ import annotations

import json
import os
import tempfile

from . import aliases
from .config import BASE_URL, UPCOMING_JSON, UPCOMING_STATE_JSON

# Keys carrying GUIDs that must never reach the public file.
_GUID_KEYS = ("tournament_guid", "player_guid", "guid", "profile_guid")


def _strip_guids(obj):
    if isinstance(obj, dict):
        return {k: _strip_guids(v) for k, v in obj.items() if k not in _GUID_KEYS}
    if isinstance(obj, list):
        return [_strip_guids(x) for x in obj]
    return obj


def assemble_upcoming(raw: dict, alias_map: dict, now_iso: str) -> dict:
    public = _strip_guids(raw)
    for t in public.get("tournaments", []):
        for e in t.get("entries", []):
            e["player"] = aliases.apply(e["player"], alias_map)
    public["generated_at"] = now_iso
    return public


def write_outputs(public: dict, private: dict) -> None:
    _atomic_write(UPCOMING_JSON, public)
    UPCOMING_STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(UPCOMING_STATE_JSON, private)


def _atomic_write(path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(path))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def run_upcoming() -> dict:  # pragma: no cover - exercised manually (Task 12)
    """Full scrape: confirmed friends -> upcoming entries -> draws + order-of-play
    -> per-friend paths -> write public + private JSON. Returns the public dict."""
    from datetime import datetime

    from playwright.sync_api import sync_playwright

    from .client import dismiss_cookies, ensure_login, new_context
    from .fetch import load_players
    from .upcoming_parse import find_upcoming_entries, parse_draw, parse_order_of_play
    from .upcoming_path import build_path

    today = datetime.now().astimezone().date().isoformat()
    players = load_players()
    raw = {"tournaments": []}
    tour_index: dict[str, dict] = {}

    with sync_playwright() as p:
        browser, ctx = new_context(p)
        page = ensure_login(ctx)
        for pl in players:
            page.goto(f"{BASE_URL}/player-profile/{pl['guid']}/tournaments",
                      wait_until="domcontentloaded")
            dismiss_cookies(page)
            page.wait_for_timeout(1200)
            entries = find_upcoming_entries(page.content(), today)
            for ent in entries:
                guid = ent["tournament_guid"]
                if not guid:
                    continue
                t = tour_index.get(guid)
                if t is None:
                    # Load draws list to find this event's draw index, then the draw + matches.
                    draws_html, draw_index = _resolve_event_draw(page, guid, ent["event"])
                    draw_rounds = parse_draw(_load(page, f"{BASE_URL}/tournament/{guid}/draw/{draw_index}")) if draw_index else []
                    schedule = _load_schedule(page, guid, ent)
                    t = {"name": ent["tournament"], "tournament_guid": guid,
                         "venue": "", "start_date": ent["start_date"],
                         "end_date": ent["end_date"], "status": "order_published" if schedule else "draw_published",
                         "entries": [], "_rounds": draw_rounds, "_schedule": schedule}
                    tour_index[guid] = t
                    raw["tournaments"].append(t)
                path = build_path(t["_rounds"], t["_schedule"],
                                  pl["nickname"] or pl["full_name"], ent["event"], today)
                t["entries"].append({"player": pl["nickname"] or pl["full_name"],
                                     "player_guid": pl["guid"], "event": ent["event"],
                                     "path": path})
            page.wait_for_timeout(800)  # politeness
        browser.close()

    for t in raw["tournaments"]:
        t.pop("_rounds", None)
        t.pop("_schedule", None)

    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    public = assemble_upcoming(json.loads(json.dumps(raw)), aliases.alias_map(), now_iso)
    private = dict(raw)
    private["generated_at"] = now_iso
    write_outputs(public, private)
    return public


def _load(page, url: str) -> str:  # pragma: no cover
    from .client import dismiss_cookies
    page.goto(url, wait_until="domcontentloaded")
    dismiss_cookies(page)
    page.wait_for_timeout(900)
    return page.content()


def _resolve_event_draw(page, guid: str, event: str):  # pragma: no cover
    """Return (draws_html, draw_index|None) by matching the event label in the draws list."""
    import re
    html = _load(page, f"{BASE_URL}/sport/draws.aspx?id={guid}")
    # td.drawname links carry draw={N}; match the row whose text contains the event code.
    for m in re.finditer(r'draw=(\d+)[^>]*>(.*?)</a>', html, re.S):
        idx, label = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2))
        if event.split()[0].lower() in label.lower():
            return html, idx
    return html, None


def _load_schedule(page, guid: str, ent: dict):  # pragma: no cover
    """Load each tournament day's Matches page, parse order-of-play rows."""
    from .upcoming_parse import parse_order_of_play
    rows = []
    for day in _day_range(ent.get("start_date"), ent.get("end_date")):
        html = _load(page, f"{BASE_URL}/tournament/{guid}/matches/{day.replace('-', '')}")
        rows.extend(parse_order_of_play(html, day))
    return rows


def _day_range(start: str | None, end: str | None):  # pragma: no cover
    from datetime import date, timedelta
    if not start:
        return []
    s = date.fromisoformat(start)
    e = date.fromisoformat(end) if end else s
    out, cur = [], s
    while cur <= e:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out
```

- [ ] **Step 4: Wire the CLI**

In `src/badminton_tracker/__main__.py`, add the subparser (after the `server` block, before `args = parser.parse_args()`):

```python
    p_upc = sub.add_parser("upcoming", help="scrape upcoming draws/schedule -> web/upcoming.json")
    p_upc.add_argument("--watch", action="store_true", help="loop, self-pacing the refresh")
```

And add the dispatch branch (after the `server` branch):

```python
    elif args.command == "upcoming":
        from .upcoming_build import run_upcoming

        if args.watch:
            from .upcoming_schedule import watch

            watch(run_upcoming)
        else:
            run_upcoming()
```

- [ ] **Step 5: Run test + verify CLI parses**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_build.py -v`
Expected: both PASS.
Run: `~/.local/bin/uv.exe run badminton upcoming --help`
Expected: shows the `--watch` flag, no import error.

- [ ] **Step 6: Lint + commit**

Run: `~/.local/bin/uv.exe run ruff check src/badminton_tracker/upcoming_build.py src/badminton_tracker/__main__.py`
Expected: no errors.

```bash
git add src/badminton_tracker/upcoming_build.py src/badminton_tracker/__main__.py tests/test_upcoming_build.py
git commit -m "Add upcoming_build orchestrator (pure assembler + Playwright driver) + CLI verb"
```

---

## Task 9: Frontend — load `upcoming.json` + `formatChatText` mirror

**Files:**
- Modify: `web/app.js` (boot loader + new helpers)

**Interfaces:**
- Consumes: `upcoming.json` shape from Task 8; `fetchJSON` already in `app.js`.
- Produces (in `app.js`): global `UPC` (loaded upcoming data or null);
  `formatChatText(upc, options)` mirroring Task 7's Python output;
  `upcomingActive()` → bool (any tournament whose window includes today).

- [ ] **Step 1: Load `upcoming.json` in `boot()`**

In `web/app.js`, add a global near `let DB = null;`:

```javascript
let UPC = null;  // upcoming-tournament data (may be absent on bare deploys)
```

In `boot()`, after the `DB = live || snap;` block and before `setMeta();`, add:

```javascript
  // Upcoming timeline data — prefer live container, fall back to published snapshot.
  try { UPC = await fetchJSON((API_BASE ? API_BASE : ".") + "/upcoming.json", 4000); }
  catch (_) { try { UPC = await fetchJSON("./upcoming.json"); } catch (_) { UPC = null; } }
```

- [ ] **Step 2: Add `formatChatText` + `upcomingActive` helpers**

Add near the other data helpers (after `playerMatches`):

```javascript
function upcomingActive() {
  if (!UPC || !UPC.tournaments) return false;
  const today = new Date().toISOString().slice(0, 10);
  return UPC.tournaments.some((t) => t.start_date && t.end_date &&
    t.start_date <= today && today <= t.end_date);
}

function upcClock(iso, notBefore) {
  if (!iso) return "";
  const hhmm = iso.length >= 16 ? iso.slice(11, 16) : "";
  return notBefore && hhmm ? "~" + hhmm : hhmm;
}

// Mirrors src/badminton_tracker/upcoming_text.py::format_chat_text
function formatChatText(upc, opts) {
  const players = opts.players || null;
  const tours = opts.tournaments || null;
  const horizon = opts.horizon || "next";
  const fields = new Set(opts.fields || ["court", "opponent"]);
  const showProjected = fields.has("projected") || horizon === "full";
  const lineFor = (player, event, n) => {
    const parts = [`${player} (${event}): ${n.round}`];
    if (n.state === "scheduled" || n.state === "done") {
      const clk = upcClock(n.time, n.time_kind === "not_before");
      if (clk) parts.push(clk);
      if (fields.has("court") && n.court) parts.push("Court " + n.court);
      if (fields.has("opponent") && n.opponent) parts.push("vs " + n.opponent);
    } else {
      const when = n.session || n.day || "";
      parts.push(`${n.opponent || "TBD"} (${when})`.trim());
    }
    return parts.join(" ");
  };
  const relevant = (path) => {
    const up = path.filter((n) => n.state === "scheduled" || n.state === "projected");
    if (horizon === "next") {
      const sched = up.find((n) => n.state === "scheduled");
      return sched ? [sched] : up.slice(0, 1);
    }
    return up;
  };
  const out = [];
  for (const t of (upc.tournaments || [])) {
    if (tours && !tours.includes(t.name)) continue;
    const lines = [];
    for (const e of (t.entries || [])) {
      if (players && !players.includes(e.player)) continue;
      for (const n of relevant(e.path)) {
        if (n.state === "projected" && !showProjected) continue;
        lines.push(lineFor(e.player, e.event, n));
      }
    }
    if (lines.length) { out.push("🏸 " + t.name); out.push(...lines); }
  }
  return out.join("\n");
}
```

- [ ] **Step 3: Manual smoke check**

Create a minimal `web/upcoming.json` by hand (copy the `UPCOMING` example from Task 7's test, add `"generated_at"`), then:

Run: `~/.local/bin/uv.exe run badminton serve --port 8000` (background), open `http://localhost:8000`, and in the browser console run:
`formatChatText(UPC, {players:["Chau"], horizon:"next", fields:["court","opponent"]})`
Expected: returns a string like `"🏸 Stadin\nChau (MS B): QF ~13:30 Court K3 vs Real Opponent"`.

- [ ] **Step 4: Commit**

```bash
git add web/app.js
git commit -m "Frontend: load upcoming.json + formatChatText/upcomingActive helpers"
```

---

## Task 10: Frontend — `viewUpcoming` timeline + hero + filter/export UI

**Files:**
- Modify: `web/app.js` (new view + router case)
- Modify: `web/index.html` (nav link)
- Modify: `web/styles.css` (timeline/hero/state/filter/export styles)

**Interfaces:**
- Consumes: `UPC`, `formatChatText`, `upcomingActive`, existing `esc`, `app`,
  router `switch`, nav `data-route` toggling.
- Produces: `viewUpcoming()`; router `case "upcoming"`; `#nav-upcoming` link.

- [ ] **Step 1: Add the nav link**

In `web/index.html`, inside `<nav class="nav" id="nav">`, add after the Tournaments link:

```html
        <a href="#/upcoming" data-route="upcoming" id="nav-upcoming">Upcoming</a>
```

- [ ] **Step 2: Add `viewUpcoming()` to `web/app.js`**

Add near the other view functions (before the router):

```javascript
function viewUpcoming() {
  if (!UPC || !UPC.tournaments || !UPC.tournaments.length) {
    return notFound("No upcoming tournaments tracked right now.");
  }
  // Filter state lives on the URL-free module scope; default = all players.
  const allPlayers = [...new Set(UPC.tournaments.flatMap(
    (t) => (t.entries || []).map((e) => e.player)))];
  window.__upcFilter = window.__upcFilter || new Set(allPlayers);
  const sel = window.__upcFilter;

  const stateClass = (s) => "tl__node tl__node--" + s;
  const nodeTime = (n) => {
    if (n.time) return upcClock(n.time, n.time_kind === "not_before") +
      (n.court ? " · Court " + esc(n.court) : "");
    if (n.day) return esc(n.session || n.day);
    return "";
  };
  const heroFor = (e) => {
    const next = e.path.find((n) => n.state === "scheduled");
    if (!next) return "";
    const opp = next.opponent ? "vs " + esc(next.opponent) : "";
    return `<div class="hero-up">
      <div class="hero-up__lead">⏱ NEXT · ${esc(e.player)} · ${esc(next.round)}</div>
      <div class="hero-up__opp">${opp}</div>
      <div class="hero-up__meta">${nodeTime(next)}</div>
      <div class="hero-up__cd" data-time="${esc(next.time || "")}"></div>
    </div>`;
  };
  const pathHtml = (e) => e.path.map((n, i) => {
    const prevDone = i > 0 && e.path[i - 1].state === "done";
    const here = n.state !== "done" && prevDone ? `<div class="tl__here">you are here</div>` : "";
    const right = n.state === "done"
      ? `<span class="tl__res">${esc(n.result || "")}</span>`
      : `<span class="tl__opp">${esc(n.opponent || "TBD")}</span>`;
    return `${here}<div class="${stateClass(n.state)}">
      <span class="tl__round">${esc(n.round)}</span>
      ${right}
      <span class="tl__when">${nodeTime(n)}</span></div>`;
  }).join("");

  const chips = allPlayers.map((p) =>
    `<button class="chip ${sel.has(p) ? "chip--on" : ""}" data-p="${esc(p)}">${esc(p)}</button>`
  ).join("");

  const blocks = UPC.tournaments.map((t) => {
    const entries = (t.entries || []).filter((e) => sel.has(e.player));
    if (!entries.length) return "";
    const hero = entries.map(heroFor).join("");
    const paths = entries.map((e) =>
      `<div class="tl"><div class="tl__title">${esc(e.player)} · ${esc(e.event)}</div>${pathHtml(e)}</div>`
    ).join("");
    return `<section class="block">
      <div class="block__head"><h2 class="section-title">${esc(t.name)}</h2>
        <span class="tag">${esc(t.start_date || "")}–${esc(t.end_date || "")}</span></div>
      ${hero}${paths}</section>`;
  }).join("");

  app.innerHTML = `
    <div class="upc-bar">
      <div class="chips">${chips}</div>
      <button class="tag" id="upc-export">Copy for chat</button>
    </div>
    <div id="upc-export-panel" class="upc-panel" hidden></div>
    ${blocks || `<div class="empty" style="padding:60px">No matches for the selected players.</div>`}
  `;

  // Chip toggles
  app.querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => {
    const p = b.dataset.p;
    if (sel.has(p)) sel.delete(p); else sel.add(p);
    viewUpcoming();
  }));

  // Live countdowns
  app.querySelectorAll(".hero-up__cd").forEach((el) => {
    const iso = el.dataset.time;
    if (!iso) return;
    const tick = () => {
      const diff = new Date(iso) - new Date();
      if (diff <= 0) { el.textContent = "starting / underway"; return; }
      const h = Math.floor(diff / 3600000), m = Math.floor((diff % 3600000) / 60000);
      el.textContent = `Starts in ~${h ? h + "h " : ""}${m}m · be there ~${
        new Date(new Date(iso) - 30 * 60000).toTimeString().slice(0, 5)}`;
    };
    tick();
  });

  // Export panel
  document.getElementById("upc-export").addEventListener("click", () =>
    renderUpcExport(allPlayers, sel));
}

function renderUpcExport(allPlayers, sel) {
  const panel = document.getElementById("upc-export-panel");
  panel.hidden = false;
  panel.innerHTML = `
    <label><input type="radio" name="horizon" value="next" checked> Next match only</label>
    <label><input type="radio" name="horizon" value="full"> Full path to final</label>
    <label><input type="checkbox" class="fld" value="court" checked> Court</label>
    <label><input type="checkbox" class="fld" value="opponent" checked> Opponent</label>
    <label><input type="checkbox" class="fld" value="projected"> Projected rounds</label>
    <button class="tag" id="upc-copy">Copy</button>
    <pre id="upc-preview" class="upc-preview"></pre>`;
  const build = () => {
    const horizon = panel.querySelector('input[name="horizon"]:checked').value;
    const fields = [...panel.querySelectorAll(".fld:checked")].map((c) => c.value);
    const txt = formatChatText(UPC, { players: [...sel], horizon, fields });
    panel.querySelector("#upc-preview").textContent = txt;
    return txt;
  };
  panel.querySelectorAll("input").forEach((i) => i.addEventListener("change", build));
  document.getElementById("upc-copy").addEventListener("click", () => {
    const txt = build();
    navigator.clipboard.writeText(txt).then(() => {
      document.getElementById("upc-copy").textContent = "Copied!";
    });
  });
  build();
}
```

- [ ] **Step 3: Wire the router**

In `web/app.js` `router()` switch, add before `case "maintain"`:

```javascript
    case "upcoming": return viewUpcoming();
```

- [ ] **Step 4: Add styles**

Append to `web/styles.css`:

```css
/* ── Upcoming timeline ─────────────────────────────────────────── */
.upc-bar { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:16px; flex-wrap:wrap; }
.chips { display:flex; gap:8px; flex-wrap:wrap; }
.chip { border:1px solid var(--line, #ccc); background:transparent; border-radius:999px; padding:4px 12px; cursor:pointer; font:inherit; }
.chip--on { background:var(--ink, #222); color:var(--paper, #fff); }
.hero-up { border:2px solid var(--ink, #222); border-radius:14px; padding:16px; margin:12px 0; }
.hero-up__lead { font-weight:700; letter-spacing:.02em; }
.hero-up__opp { font-size:1.3rem; margin:4px 0; }
.hero-up__meta, .hero-up__cd { opacity:.8; font-family:"Space Mono", monospace; font-size:.9rem; }
.tl { margin:14px 0; }
.tl__title { font-weight:600; margin-bottom:6px; }
.tl__node { display:grid; grid-template-columns:auto 1fr auto; gap:10px; align-items:center;
  padding:8px 12px; border-left:3px solid var(--line, #ccc); margin-left:6px; }
.tl__node--done { opacity:.55; }
.tl__node--scheduled { border-left-color:var(--accent, #2a7); }
.tl__node--projected { border-left-style:dashed; opacity:.7; }
.tl__round { font-weight:700; font-family:"Space Mono", monospace; }
.tl__when { font-family:"Space Mono", monospace; font-size:.85rem; opacity:.85; }
.tl__here { font-size:.75rem; text-transform:uppercase; letter-spacing:.08em; opacity:.6; margin:6px 0 2px 6px; }
.upc-panel { border:1px solid var(--line, #ccc); border-radius:12px; padding:12px; margin-bottom:16px;
  display:flex; gap:14px; flex-wrap:wrap; align-items:center; }
.upc-panel label { display:flex; gap:4px; align-items:center; font-size:.9rem; }
.upc-preview { width:100%; white-space:pre-wrap; background:rgba(0,0,0,.04); border-radius:8px; padding:10px; font-family:"Space Mono", monospace; font-size:.85rem; }
@media (max-width:520px){ .tl__node{ grid-template-columns:auto 1fr; } .tl__when{ grid-column:2; } }
```

- [ ] **Step 5: Manual verification**

Run: `~/.local/bin/uv.exe run badminton serve --port 8000` (background). Open
`http://localhost:8000/#/upcoming` (with the hand-made `web/upcoming.json` from
Task 9). Verify: timeline renders, hero shows countdown, player chips filter,
"Copy for chat" opens the panel and produces text. Take a screenshot.

- [ ] **Step 6: Commit**

```bash
git add web/app.js web/index.html web/styles.css
git commit -m "Frontend: viewUpcoming timeline + hero countdown + filter chips + chat export"
```

---

## Task 11: Home-page takeover during active window

**Files:**
- Modify: `web/app.js` (`viewGroup`)

**Interfaces:**
- Consumes: `upcomingActive`, `UPC`, existing `viewGroup` markup.
- Produces: a "Next up" hero block at the top of the group page when active.

- [ ] **Step 1: Add the takeover block to `viewGroup`**

In `web/app.js` `viewGroup()`, locate where it sets `app.innerHTML = ...` and prepend a banner when a tournament is active. Insert at the start of the function:

```javascript
  let upcHero = "";
  if (upcomingActive()) {
    const next = [];
    for (const t of UPC.tournaments) {
      for (const e of (t.entries || [])) {
        const n = e.path.find((x) => x.state === "scheduled");
        if (n) next.push(`${esc(e.player)} · ${esc(n.round)} ${
          n.time ? upcClock(n.time, n.time_kind === "not_before") : ""}${
          n.court ? " · Court " + esc(n.court) : ""}`);
      }
    }
    if (next.length) {
      upcHero = `<a class="up-takeover rise" href="#/upcoming">
        <span class="up-takeover__tag">Happening now</span>
        <span class="up-takeover__list">${next.slice(0, 4).join("  ·  ")}</span>
        <span class="tag">see timeline →</span></a>`;
    }
  }
```

Then prepend `upcHero` to the existing `app.innerHTML` string (e.g. change
`app.innerHTML = \`<section...` to `app.innerHTML = upcHero + \`<section...`).

- [ ] **Step 2: Add styles**

Append to `web/styles.css`:

```css
.up-takeover { display:flex; gap:12px; align-items:center; flex-wrap:wrap;
  border:2px solid var(--accent, #2a7); border-radius:14px; padding:12px 16px; margin-bottom:18px; text-decoration:none; color:inherit; }
.up-takeover__tag { font-weight:700; color:var(--accent, #2a7); text-transform:uppercase; font-size:.8rem; letter-spacing:.06em; }
.up-takeover__list { flex:1; font-family:"Space Mono", monospace; font-size:.9rem; }
```

- [ ] **Step 3: Manual verification**

With the hand-made `upcoming.json` dated to include today, reload
`http://localhost:8000/#/` and confirm the "Happening now" bar appears above the
standings and links to `#/upcoming`. Edit the JSON dates to the past and confirm
it disappears. Screenshot both.

- [ ] **Step 4: Commit**

```bash
git add web/app.js web/styles.css
git commit -m "Frontend: home-page takeover banner during active tournament window"
```

---

## Task 12: Live scrape verification + privacy gate + deploy wiring

**Files:**
- Modify: deployment config (`docker-compose.yml` or the windows start script) to run `badminton upcoming --watch`.
- No new tests (this is integration + verification).

**Interfaces:**
- Consumes: everything above. Produces a real `web/upcoming.json` +
  `data/upcoming_state.json` from the live site, and a running watcher.

- [ ] **Step 1: One real scrape**

Run (needs `.env` creds): `~/.local/bin/uv.exe run badminton upcoming`
Expected: writes `web/upcoming.json` and `data/upcoming_state.json`; prints no
traceback. If selectors miss (empty paths), capture the live HTML into the
`tests/fixtures/upcoming/` files, fix the parser, re-run the parser tests.

- [ ] **Step 2: PRIVACY GATE (rule #4) — must pass before any commit/push**

Run:
```bash
grep -E '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}' web/upcoming.json && echo "LEAK!" || echo "clean (no GUIDs)"
grep -E 'profile_guid|player-profile|tournament_guid|player_guid' web/upcoming.json && echo "LEAK!" || echo "clean (no guid keys)"
```
Expected: both print "clean". If "LEAK!", stop and fix `_strip_guids`/`_GUID_KEYS`.

- [ ] **Step 3: Verify the view against real data**

Run: `~/.local/bin/uv.exe run badminton serve --port 8000` (background). Open
`http://localhost:8000/#/upcoming`. Confirm a real entry renders with its path.
Screenshot.

- [ ] **Step 4: Commit private state to the data repo**

```bash
git -C data add upcoming_state.json
git -C data commit -m "Add upcoming-tournament scrape state"
```

- [ ] **Step 5: Commit public artifact to the public repo**

```bash
git add web/upcoming.json
git commit -m "Add first scraped upcoming.json snapshot"
```

- [ ] **Step 6: Wire the watcher into the home server**

Add a second always-on command to the deployment. In `docker-compose.yml`, add a
service mirroring the web one but with the upcoming command (shares the same
image, mounts `./data` and `./web`, same `.env`):

```yaml
  upcoming:
    build: .
    command: ["uv", "run", "badminton", "upcoming", "--watch"]
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./web:/app/web
    restart: unless-stopped
```

(If the project uses the no-Docker path, add a parallel `windows\run-upcoming.bat`
calling `uv run badminton upcoming --watch` and document it in SETUP.md.)

- [ ] **Step 7: Verify the watcher starts**

Run: `docker compose up -d --build` (or the no-Docker bat), then check the
`upcoming` service logs show one scrape + a computed sleep. `GET /api/health`
still returns ok.

- [ ] **Step 8: Commit deploy wiring**

```bash
git add docker-compose.yml SETUP.md
git commit -m "Deploy: run upcoming --watch as an always-on home-server service"
```

---

## Self-Review

**Spec coverage:**
- End-to-end scraper + viz → Tasks 2–8 (data) + 9–11 (viz). ✅
- Auto from profiles → `find_upcoming_entries` over every confirmed player (Task 4, Task 8 loop). ✅
- Self-paced refresh → `next_refresh_delay` (Task 6), `--watch` (Task 8), deploy (Task 12). ✅
- Public draw = public data (opponents verbatim, no GUIDs) → `assemble_upcoming`/`_strip_guids` keeps opponents, strips GUIDs (Task 8); privacy gate (Task 12). ✅
- Both placements (Upcoming tab + home takeover) → Tasks 10 & 11. ✅
- Vertical timeline phone-first → Task 10 + responsive CSS. ✅
- Player filter → chips (Task 10). ✅
- Chat-text export with options (players / horizon / detail / tournament) → Task 7 (Python spec) + Task 9/10 (UI). ✅
- Three states (done/scheduled/projected), decaying confidence → `build_path` (Task 5), rendered Task 10. ✅
- "Be at venue by" + countdown → Task 10 hero. ✅
- Atomic writes / never publish partial → `_atomic_write` (Task 8). ✅
- Tests over fixtures, no network → Tasks 1–7. ✅

**Deferred (per spec non-goals):** `.ics` export, manual-refresh button (sentinel hook left in `watch`), full-bracket zoom-out. Not planned. ✅

**Type consistency:** node dict shape (`round/state/opponent/result/court/time/time_kind/day/session`) is identical across `build_path` (Task 5), `format_chat_text` (Task 7), `formatChatText` JS (Task 9), `viewUpcoming` (Task 10). Schedule-row shape (`event/round_label/time/court/players/date/result`) consistent between `parse_order_of_play` (Task 3) and `build_path` (Task 5). `find_upcoming_entries` output (`tournament/tournament_guid/event/start_date/end_date`) consumed in Task 8. ✅

**Note for implementer:** `parse_order_of_play` does not set `result` (it's an order-of-play page); `build_path` treats a missing `result` as not-done. If a Matches row for a completed match carries a score, a future enhancement can populate `result` there — out of scope for v1 (done-state primarily comes from the historical data; the upcoming view focuses on scheduled/projected).

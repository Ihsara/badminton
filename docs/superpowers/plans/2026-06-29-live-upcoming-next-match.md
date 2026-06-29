# Live auto-recheck + readable next-match view — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the upcoming-tournament timeline refresh itself live and unattended, and add a readable per-player "next match" view with a tournament link.

**Architecture:** A tighter self-pacing cadence + an unattended-safe watcher (persisted cookie, no crash-loop) feed `web/upcoming.json`; a host scheduled task publishes it (graceful, ff-only); the frontend gains a "next match" summary block (linked via the now-public tournament GUID) and a 2-min poll so an open tab self-updates.

**Tech Stack:** Python 3.13 via `uv`, pytest, ruff; vanilla JS frontend (`web/app.js`); Docker Compose; Windows host `.bat` + `install-autostart.ps1`.

**Design spec:** `docs/superpowers/specs/2026-06-29-live-upcoming-next-match-design.md`

## Global Constraints

- **Python only via `uv`** — never bare `pip`/`python`. The agent shell may lack `uv` on PATH; call it as `~/.local/bin/uv.exe` if `uv` is not found.
- **Lint with ruff** before claiming clean: `~/.local/bin/uv.exe run ruff check`.
- **Privacy is the architecture.** Player/profile GUIDs must NEVER reach `web/upcoming.json`. The *tournament* GUID is public and is now allowed in the public file; nothing else GUID-shaped is.
- **Two identities.** Public pushes go to `Ihsara/badminton` as the Ihsara gh account. Data commits go to the private `data/` repo. Never `git add` anything under `data/`, `.env`, or `out/` to the public repo.
- **Helsinki summer offset** for times is `+03:00` (already emitted by the parser).
- **Stadin tournament GUID:** `1A563200-14BA-4328-955A-922A5EEC6374`.
- **Public site host:** `badmintonfinland.tournamentsoftware.com`.
- Run the full suite with `~/.local/bin/uv.exe run pytest -q` after each task; keep output pristine.

---

### Task 1: Tighten the refresh cadence (5 min / 10 min)

**Files:**
- Modify: `src/badminton_tracker/upcoming_schedule.py:13-16` (constants), `:38-61` (`next_refresh_delay`)
- Test: `tests/test_upcoming_schedule.py:32-38` (update existing 15m test), add new 10m test

**Interfaces:**
- Consumes: nothing new.
- Produces: `next_refresh_delay(state: dict, now: datetime) -> int` returns `300` (imminent ≤2h), `600` (match day, order published), `21600` (≤3 days out), `86400` (idle). Constants `FIVE_MIN=300`, `TEN_MIN=600` replace `FIFTEEN_MIN`/`THIRTY_MIN`.

- [ ] **Step 1: Update the two cadence tests to the new floors**

In `tests/test_upcoming_schedule.py`, change `test_match_day_order_published_polls_30m` and `test_friend_match_within_2h_polls_15m` to the new values and rename them:

```python
def test_match_day_order_published_polls_10m():
    now = datetime(2026, 3, 14, 8, 0, tzinfo=TZ)  # on start day
    assert next_refresh_delay(_state(status="order_published"), now) == 600


def test_friend_match_within_2h_polls_5m():
    now = datetime(2026, 3, 14, 12, 0, tzinfo=TZ)
    st = _state(status="order_published",
                entries=[{"player": "Chau", "event": "MS B",
                          "path": [{"round": "QF", "state": "scheduled",
                                    "time": "2026-03-14T13:30:00+02:00"}]}])
    assert next_refresh_delay(st, now) == 300
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_schedule.py -q`
Expected: FAIL — `test_friend_match_within_2h_polls_5m` gets `900 != 300`; `test_match_day_order_published_polls_10m` gets `1800 != 600`.

- [ ] **Step 3: Update the constants and the two return sites**

In `src/badminton_tracker/upcoming_schedule.py`, replace lines 13-16:

```python
DAILY = 86400
SIX_HOURS = 21600
TEN_MIN = 600
FIVE_MIN = 300
```

In `next_refresh_delay`, change the imminent return (was `return FIFTEEN_MIN`) to `return FIVE_MIN`, and the match-day line (was `best = min(best, THIRTY_MIN)`) to `best = min(best, TEN_MIN)`.

- [ ] **Step 4: Run the full suite to verify green**

Run: `~/.local/bin/uv.exe run pytest -q`
Expected: PASS (all). Then `~/.local/bin/uv.exe run ruff check src/badminton_tracker/upcoming_schedule.py tests/test_upcoming_schedule.py` → "All checks passed!"

- [ ] **Step 5: Commit**

```bash
git add src/badminton_tracker/upcoming_schedule.py tests/test_upcoming_schedule.py
git commit -m "feat: tighten upcoming refresh floor to 5min/10min near match time"
```

---

### Task 2: Make `watch()` unattended-safe (no crash-loop, back off on failure)

**Files:**
- Modify: `src/badminton_tracker/upcoming_schedule.py:64-71` (`watch`)
- Test: `tests/test_upcoming_schedule.py` (add a test using an injected `run_once` and a fake sleep)

**Interfaces:**
- Consumes: `next_refresh_delay`, `SIX_HOURS`.
- Produces: `watch(run_once, *, sleep=time.sleep, now_fn=...)` — on a `run_once()` exception, it must NOT propagate; it logs, sleeps `SIX_HOURS`, and continues. The injectable `sleep`/`now_fn` exist only so the loop is testable (one iteration then stop via a sentinel exception from the fake sleep).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_upcoming_schedule.py`:

```python
def test_watch_backs_off_on_failure_without_propagating():
    from badminton_tracker.upcoming_schedule import SIX_HOURS, watch

    calls = {"run": 0}
    slept = []

    def run_once():
        calls["run"] += 1
        raise RuntimeError("login failed")

    class _Stop(Exception):
        pass

    def fake_sleep(secs):
        slept.append(secs)
        raise _Stop  # break the infinite loop after the first sleep

    def fake_now():
        return datetime(2026, 1, 1, 12, 0, tzinfo=TZ)

    try:
        watch(run_once, sleep=fake_sleep, now_fn=fake_now)
    except _Stop:
        pass

    assert calls["run"] == 1            # the failure did not propagate out of run_once
    assert slept == [SIX_HOURS]         # it backed off to the daily-ish floor, not a tight spin
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_schedule.py::test_watch_backs_off_on_failure_without_propagating -v`
Expected: FAIL — `watch()` currently takes only `run_once` (TypeError on `sleep=`), and it does not catch exceptions.

- [ ] **Step 3: Rewrite `watch()` to be injectable and exception-safe**

Replace `src/badminton_tracker/upcoming_schedule.py:64-71` with:

```python
def watch(run_once, *, sleep=time.sleep, now_fn=lambda: datetime.now().astimezone()):
    """Repeatedly run `run_once()` (which returns the freshly-built state dict),
    then sleep until the computed next refresh. A failed refresh is logged and
    backed off (SIX_HOURS) rather than propagated, so the always-on container
    never crash-loops while the user is away — the last good upcoming.json stays
    in place and the next tick self-heals."""
    while True:
        try:
            state = run_once()
            delay = next_refresh_delay(state or {}, now_fn())
        except Exception as exc:  # noqa: BLE001 - unattended loop must not die
            print(f"[upcoming] refresh failed: {exc!r}; backing off {SIX_HOURS}s")
            delay = SIX_HOURS
        sleep(delay)
```

Keep the `# pragma: no cover` off now that there is a test; if ruff/coverage config complains, leave the function uncovered branches as-is — the test covers the failure path.

- [ ] **Step 4: Run the suite and lint**

Run: `~/.local/bin/uv.exe run pytest -q` → PASS.
Run: `~/.local/bin/uv.exe run ruff check src/badminton_tracker/upcoming_schedule.py tests/test_upcoming_schedule.py` → "All checks passed!"

- [ ] **Step 5: Commit**

```bash
git add src/badminton_tracker/upcoming_schedule.py tests/test_upcoming_schedule.py
git commit -m "fix: watch() backs off on failure instead of crash-looping (unattended)"
```

---

### Task 3: Allow the tournament GUID in the public file (narrow GUID stripping)

**Files:**
- Modify: `src/badminton_tracker/upcoming_build.py:20` (`_GUID_KEYS`)
- Test: `tests/test_upcoming_build.py:7-30` (update existing assertion), add a player-leak regression test

**Interfaces:**
- Consumes: nothing new.
- Produces: `assemble_upcoming(raw, alias_map, now_iso)` output now **retains** `tournament_guid` values and **strips** `player_guid`, `profile_guid`, and any `guid` key. No player/profile GUID may appear in the output.

- [ ] **Step 1: Update the existing strip test + add a leak-regression test**

In `tests/test_upcoming_build.py`, in `test_assemble_strips_guids_and_applies_aliases`, replace the tournament-guid assertion. Change:

```python
    assert "AAAA1111" not in blob  # tournament guid stripped
```
to:
```python
    assert "AAAA1111-2222-3333-4444-555566667777" in blob  # tournament guid is PUBLIC, kept
    assert out["tournaments"][0]["tournament_guid"] == "AAAA1111-2222-3333-4444-555566667777"
```

Then append a new test:

```python
def test_assemble_never_leaks_player_or_profile_guid():
    raw = {"tournaments": [{
        "name": "T", "tournament_guid": "1A563200-14BA-4328-955A-922A5EEC6374",
        "venue": "", "start_date": "2026-07-04", "end_date": "2026-07-04",
        "status": "order_published",
        "entries": [{
            "player": "Chau", "player_guid": "PLAYER-GUID-SENTINEL",
            "profile_guid": "PROFILE-GUID-SENTINEL", "event": "MS B",
            "path": [{"round": "R1", "state": "scheduled", "opponent": "X",
                      "court": None, "time": None, "time_kind": None,
                      "guid": "NESTED-GUID-SENTINEL"}],
        }],
    }]}
    out = assemble_upcoming(raw, {}, "2026-07-04T08:00:00+03:00")
    blob = repr(out)
    assert "PLAYER-GUID-SENTINEL" not in blob
    assert "PROFILE-GUID-SENTINEL" not in blob
    assert "NESTED-GUID-SENTINEL" not in blob
    assert "player_guid" not in blob and "profile_guid" not in blob
    # tournament guid is allowed through:
    assert out["tournaments"][0]["tournament_guid"] == "1A563200-14BA-4328-955A-922A5EEC6374"
```

- [ ] **Step 2: Run the build tests to verify they fail**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_build.py -q`
Expected: FAIL — current code strips `tournament_guid`, so the new `in blob` assertion fails; the new test also fails on the retained-guid assertion.

- [ ] **Step 3: Narrow `_GUID_KEYS`**

In `src/badminton_tracker/upcoming_build.py`, replace line 20:

```python
# Keys carrying PLAYER/PROFILE GUIDs that must never reach the public file.
# The tournament GUID is a public event identifier (it's the tournament's own
# page id on the site) and is deliberately KEPT so the UI can link out.
_GUID_KEYS = ("player_guid", "profile_guid", "guid")
```

- [ ] **Step 4: Run the suite and lint**

Run: `~/.local/bin/uv.exe run pytest -q` → PASS.
Run: `~/.local/bin/uv.exe run ruff check src/badminton_tracker/upcoming_build.py tests/test_upcoming_build.py` → "All checks passed!"

- [ ] **Step 5: Commit**

```bash
git add src/badminton_tracker/upcoming_build.py tests/test_upcoming_build.py
git commit -m "feat: keep public tournament_guid; still strip every player/profile guid"
```

---

### Task 4: Regenerate `web/upcoming.json` so it carries the tournament GUID

**Files:**
- Modify (data): `web/upcoming.json`, `data/upcoming_state.json` (regenerated by the run)

**Interfaces:**
- Consumes: Tasks 1 & 3 (cadence + GUID keys). Produces the public file the frontend (Task 6/7) links from.

> This task runs the live scraper. It needs the saved cookie `out/auth_state.json` and the `.env` creds. If the run returns `{"tournaments": []}` or hits a login wall, the cookie is stale — it will auto-re-auth from `.env`; if that fails, stop and report (do not fake data).

- [ ] **Step 1: Run the live pipeline (UTF-8 forced; empty shell vars unset so they don't shadow `.env`)**

```bash
unset TOURNAMENTSOFTWARE_USERNAME TOURNAMENTSOFTWARE_PASSWORD && \
  PYTHONUTF8=1 PYTHONIOENCODING=utf-8 ~/.local/bin/uv.exe run badminton upcoming \
  --tournament 1A563200-14BA-4328-955A-922A5EEC6374
```

- [ ] **Step 2: Verify the public file shape + that the tournament GUID is now present**

Run:
```bash
~/.local/bin/uv.exe run python -c "import json; d=json.load(open('web/upcoming.json',encoding='utf-8')); t=d['tournaments'][0]; print('entries', len(t['entries']), 'players', sorted({e['player'] for e in t['entries']})); print('tournament_guid', t.get('tournament_guid'))"
```
Expected: `entries 8`, 7 distinct players, and `tournament_guid 1A563200-14BA-4328-955A-922A5EEC6374`.

- [ ] **Step 3: Privacy gate — no PLAYER/PROFILE guids in the public file**

Run:
```bash
~/.local/bin/uv.exe run python -c "import json,re; b=open('web/upcoming.json',encoding='utf-8').read(); d=json.loads(b); guids=set(re.findall(r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}', b)); tg={t['tournament_guid'] for t in d['tournaments']}; leak=guids-tg; print('player/profile guid leak:', leak); assert not leak, leak; assert 'player_guid' not in b and 'profile_guid' not in b"
```
Expected: `player/profile guid leak: set()` and no assertion error.
Also: `git ls-files | grep -E 'data/|\.env'` → only `.env.example`.

- [ ] **Step 4: Commit the public data (public repo) and the private state (data repo)**

```bash
git add web/upcoming.json && git commit -m "data: regenerate upcoming.json carrying public tournament_guid"
git -C data add upcoming_state.json && git -C data commit -m "state: refresh upcoming cache"
```

---

### Task 5: Add the canonical `next_match_per_player` helper (Python, TDD)

**Files:**
- Modify: `src/badminton_tracker/upcoming_text.py` (add function)
- Test: `tests/test_upcoming_text.py` (add tests)

**Interfaces:**
- Consumes: an `upcoming` dict (the `upcoming.json` shape).
- Produces: `next_match_per_player(upcoming: dict) -> list[dict]` returning one row per (tournament, player) = that player's earliest `state == "scheduled"` node, sorted by `time` then player. Each row: `{"tournament": str, "tournament_guid": str | None, "player": str, "event": str, "node": dict}`. Players with no scheduled node are omitted.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_upcoming_text.py`:

```python
from badminton_tracker.upcoming_text import next_match_per_player


def _upc():
    return {"tournaments": [{
        "name": "Stadin", "tournament_guid": "1A563200-14BA-4328-955A-922A5EEC6374",
        "entries": [
            {"player": "Chau", "event": "MD Hobby B", "path": [
                {"round": "R1", "state": "scheduled", "opponent": "A / B",
                 "time": "2026-07-04T09:00:00+03:00"},
                {"round": "R2", "state": "scheduled", "opponent": "C / D",
                 "time": "2026-07-04T10:00:00+03:00"}]},
            {"player": "Hien", "event": "WD C", "path": [
                {"round": "R2", "state": "scheduled", "opponent": "E / F",
                 "time": "2026-07-04T10:00:00+03:00"}]},
            {"player": "Done", "event": "MS B", "path": [
                {"round": "R1", "state": "done", "opponent": "G",
                 "time": "2026-07-04T08:00:00+03:00"}]},
        ],
    }]}


def test_next_match_per_player_picks_earliest_scheduled_sorted():
    rows = next_match_per_player(_upc())
    assert [r["player"] for r in rows] == ["Chau", "Hien"]   # sorted by time, Chau 09:00 first
    assert rows[0]["node"]["round"] == "R1"                  # earliest scheduled, not R2
    assert rows[0]["node"]["opponent"] == "A / B"
    assert rows[0]["tournament"] == "Stadin"
    assert rows[0]["tournament_guid"] == "1A563200-14BA-4328-955A-922A5EEC6374"


def test_next_match_per_player_omits_players_with_no_scheduled():
    rows = next_match_per_player(_upc())
    assert all(r["player"] != "Done" for r in rows)          # only-done player dropped
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `~/.local/bin/uv.exe run pytest tests/test_upcoming_text.py -q`
Expected: FAIL — `ImportError: cannot import name 'next_match_per_player'`.

- [ ] **Step 3: Implement the helper**

Append to `src/badminton_tracker/upcoming_text.py`:

```python
def next_match_per_player(upcoming: dict) -> list[dict]:
    """One row per (tournament, player) = that player's earliest still-scheduled
    match, sorted by time then player. Players with no scheduled node are omitted.
    Mirrors the frontend's nextMatchPerPlayer in app.js."""
    rows: list[dict] = []
    for t in upcoming.get("tournaments", []):
        for e in t.get("entries", []):
            scheduled = [n for n in e.get("path", []) if n.get("state") == "scheduled"]
            if not scheduled:
                continue
            node = min(scheduled, key=lambda n: n.get("time") or "")
            rows.append({
                "tournament": t.get("name", ""),
                "tournament_guid": t.get("tournament_guid"),
                "player": e.get("player", ""),
                "event": e.get("event", ""),
                "node": node,
            })
    rows.sort(key=lambda r: (r["node"].get("time") or "", r["player"]))
    return rows
```

- [ ] **Step 4: Run the suite and lint**

Run: `~/.local/bin/uv.exe run pytest -q` → PASS.
Run: `~/.local/bin/uv.exe run ruff check src/badminton_tracker/upcoming_text.py tests/test_upcoming_text.py` → "All checks passed!"

- [ ] **Step 5: Commit**

```bash
git add src/badminton_tracker/upcoming_text.py tests/test_upcoming_text.py
git commit -m "feat: next_match_per_player helper (canonical, mirrored by frontend)"
```

---

### Task 6: Render the readable "next match" block + tournament link (frontend)

**Files:**
- Modify: `web/app.js` (add `TS_HOST` const, `nextMatchPerPlayer`, `relTime`, render block in `viewUpcoming`)
- Modify: `web/styles.css` (a small `.nextcard` block — follow existing class style)

**Interfaces:**
- Consumes: `UPC` (loaded `upcoming.json`), `esc`, `upcClock`.
- Produces: a summary block prepended in `viewUpcoming()`; `nextMatchPerPlayer(upc)` mirrors the Python helper (same ordering and fields).

> No JS test harness exists in this repo; this task is verified manually in Task 8. Keep `nextMatchPerPlayer` a pure function so its logic matches the Python test in Task 5.

- [ ] **Step 1: Add the host constant + helpers near the other upcoming utils (after `upcClock`, ~line 47)**

```javascript
// The public tournamentsoftware host — fixed and public, used to link out.
const TS_HOST = "https://badmintonfinland.tournamentsoftware.com";

// Mirrors src/badminton_tracker/upcoming_text.py::next_match_per_player
function nextMatchPerPlayer(upc) {
  const rows = [];
  for (const t of (upc?.tournaments || [])) {
    for (const e of (t.entries || [])) {
      const sched = (e.path || []).filter((n) => n.state === "scheduled");
      if (!sched.length) continue;
      const node = sched.reduce((a, b) => ((a.time || "") <= (b.time || "") ? a : b));
      rows.push({ tournament: t.name || "", tournament_guid: t.tournament_guid || null,
                  player: e.player || "", event: e.event || "", node });
    }
  }
  rows.sort((a, b) => ((a.node.time || "") + a.player).localeCompare((b.node.time || "") + b.player));
  return rows;
}

// "updated 3 min ago" from an ISO timestamp; coarse + dependency-free.
function relTime(iso) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  if (isNaN(diff)) return "";
  const m = Math.round(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  return h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;
}
```

- [ ] **Step 2: Build the block and prepend it inside `viewUpcoming()`**

In `web/app.js`, inside `viewUpcoming()` (before `app.innerHTML = ...` near line 598), build the block. Group rows by tournament so each gets its own header + link:

```javascript
  const summaryBlocks = (UPC.tournaments || []).map((t) => {
    const rows = nextMatchPerPlayer({ tournaments: [t] }).filter((r) => sel.has(r.player));
    if (!rows.length) return "";
    const link = t.tournament_guid
      ? `<a class="tag" href="${TS_HOST}/tournament/${esc(t.tournament_guid)}/" target="_blank" rel="noopener">open on tournamentsoftware →</a>`
      : "";
    const trs = rows.map((r) => {
      const clk = upcClock(r.node.time, r.node.time_kind === "not_before");
      return `<tr>
        <td class="nextcard__p">${esc(r.player)}</td>
        <td class="nextcard__t">${esc(clk)}</td>
        <td class="nextcard__r">${esc(r.node.round)}</td>
        <td class="nextcard__o">vs ${esc(r.node.opponent || "TBD")}</td>
        <td class="nextcard__e">${esc(r.event)}</td></tr>`;
    }).join("");
    return `<section class="nextcard">
      <div class="nextcard__head"><h2 class="section-title">${esc(t.name)}</h2>${link}
        <span class="tag tag--muted">updated ${esc(relTime(UPC.generated_at))}</span></div>
      <table class="nextcard__tbl"><tbody>${trs}</tbody></table></section>`;
  }).join("");
```

Then prepend `summaryBlocks` into the rendered HTML — change the `app.innerHTML = \`` template so the upc-bar is followed by `${summaryBlocks}` then the existing `${blocks ...}`:

```javascript
  app.innerHTML = `
    <div class="upc-bar">
      <div class="chips">${chips}</div>
      <button class="tag" id="upc-export">Copy for chat</button>
    </div>
    <div id="upc-export-panel" class="upc-panel" hidden></div>
    ${summaryBlocks}
    ${blocks || `<div class="empty" style="padding:60px">No matches for the selected players.</div>`}
  `;
```

- [ ] **Step 3: Add minimal styles in `web/styles.css`**

Append (match the existing token/spacing style already in the file):

```css
.nextcard { margin: 18px 0 28px; }
.nextcard__head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
.nextcard__tbl { width: 100%; border-collapse: collapse; }
.nextcard__tbl td { padding: 7px 10px; border-bottom: 1px solid var(--line, #2a2a2a); white-space: nowrap; }
.nextcard__o { white-space: normal; }
.nextcard__p { font-weight: 600; }
.tag--muted { opacity: .65; }
```

(If `--line` is not a defined token in `styles.css`, use the same border color the existing `.tl__node` / table rows use — grep `border-bottom` in `styles.css` and reuse that value.)

- [ ] **Step 4: Syntax-check the JS (no test harness)**

Run: `node --check web/app.js`
Expected: no output (exit 0). If `node` is unavailable, load the page in Task 8 and confirm no console error instead.

- [ ] **Step 5: Commit**

```bash
git add web/app.js web/styles.css
git commit -m "feat: readable per-player next-match block with tournament link"
```

---

### Task 7: Browser poll — keep an open tab live (frontend)

**Files:**
- Modify: `web/app.js` (`viewUpcoming` poll arm/clear; cleared on route change)

**Interfaces:**
- Consumes: `fetchJSON`, `API_BASE`, `UPC`, `router`.
- Produces: a single `window.__upcPoll` interval that re-fetches `upcoming.json` every 120s while the Upcoming view is mounted and re-renders only if `generated_at` changed.

- [ ] **Step 1: Arm the poll at the end of `viewUpcoming()` (after the countdown timers block, ~line 632)**

```javascript
  // Live poll: while this view is mounted, re-fetch upcoming.json every 2 min and
  // re-render if it changed. Cleared on the next render/route (see clearUpcPoll).
  clearUpcPoll();
  window.__upcPoll = setInterval(async () => {
    try {
      let fresh = null;
      if (API_BASE) fresh = await fetchJSON(API_BASE + "/upcoming.json", 4000);
      if (!fresh) fresh = await fetchJSON("./upcoming.json", 4000);
      if (fresh && fresh.generated_at !== (UPC && UPC.generated_at)) {
        UPC = fresh;
        if ((location.hash.replace(/^#\/?/, "").split("/")[0]) === "upcoming") viewUpcoming();
      }
    } catch (_) { /* offline tick — keep the last good UPC, try again next time */ }
  }, 120000);
```

- [ ] **Step 2: Add `clearUpcPoll` and call it from the router so leaving the page stops the poll**

Add near the other upcoming helpers:

```javascript
function clearUpcPoll() {
  if (window.__upcPoll) { clearInterval(window.__upcPoll); window.__upcPoll = null; }
}
```

In `router()` (line 669), add `clearUpcPoll();` and the existing timer cleanup right after `if (!DB) return;` so navigating away from Upcoming tears the poll down:

```javascript
function router() {
  if (!DB) return;
  clearUpcPoll();
  (window.__upcTimers || []).forEach((id) => clearInterval(id));
  window.__upcTimers = [];
  ...
```

(Note: `viewUpcoming` also clears `__upcTimers` itself; clearing here too is safe and covers navigation to other views.)

- [ ] **Step 3: Syntax-check**

Run: `node --check web/app.js`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add web/app.js
git commit -m "feat: 2-min browser poll so an open upcoming tab self-updates"
```

---

### Task 8: Wire the watcher to Stadin + persist the cookie (compose)

**Files:**
- Modify: `docker-compose.yml:39` (command), `:45-49` (volumes)

**Interfaces:**
- Consumes: the `badminton upcoming --watch --tournament <GUID>` CLI (already supported).
- Produces: an always-on watcher that scopes Stadin and persists `out/auth_state.json` across restarts.

- [ ] **Step 1: Add the Stadin GUID to the watcher command**

In `docker-compose.yml`, change the `upcoming` service `command` (line 39):

```yaml
    command: ["uv", "run", "badminton", "upcoming", "--watch",
              "--tournament", "1A563200-14BA-4328-955A-922A5EEC6374"]
```

- [ ] **Step 2: Mount `./out` so the auth cookie survives restarts**

In the `upcoming` service `volumes:` (after the `./web` line, ~line 49), add:

```yaml
      # Persist the Playwright auth cookie (out/auth_state.json) across restarts,
      # so the watcher reuses its session instead of re-logging in every boot.
      - ./out:/app/out
```

- [ ] **Step 3: Validate the compose file**

Run: `docker compose config >/dev/null && echo OK`
Expected: `OK` (compose parses). If Docker is not available in the agent environment, skip with a note; the home server will validate on deploy.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: watcher scopes Stadin + persists auth cookie across restarts"
```

---

### Task 9: Unattended host publish task (graceful, ff-only)

**Files:**
- Create: `windows/publish-upcoming.bat`
- Modify: `windows/install-autostart.ps1` (register the scheduled task)

**Interfaces:**
- Consumes: a host authenticated as Ihsara for `origin`; the privacy-gate Python one-liner.
- Produces: a scheduled task that, every ~5 min, publishes a changed `web/upcoming.json` and never wedges.

> Mirror `windows/redeploy.bat`'s shape and guards. The script must: pull `--ff-only` first; if that fails (diverged), log + exit 0 (skip, never force); run the privacy gate and abort the push on any player/profile-GUID leak; `git add` ONLY `web/upcoming.json`.

- [ ] **Step 1: Create `windows/publish-upcoming.bat`**

```bat
@echo off
REM ---------------------------------------------------------------------------
REM Unattended publish of the live upcoming.json to the PUBLIC repo (Ihsara).
REM Runs on a schedule (see install-autostart.ps1). Graceful by design:
REM   - pulls --ff-only first; if branches diverged it SKIPS (never forces),
REM   - privacy-gates the file (aborts on any player/profile GUID leak),
REM   - stages ONLY web/upcoming.json, commits + pushes, retries next tick.
REM Requires: host authenticated as Ihsara for origin (see SETUP.md).
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0\.."

REM Nothing changed? exit quietly.
git diff --quiet -- web/upcoming.json
if %errorlevel%==0 (
  echo [pub-upc] no change; nothing to do.
  exit /b 0
)

REM Privacy gate: abort if any GUID that isn't a tournament_guid is present.
~\.local\bin\uv.exe run python -c "import json,re,sys; b=open('web/upcoming.json',encoding='utf-8').read(); d=json.loads(b); g=set(re.findall(r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}',b)); tg={t.get('tournament_guid') for t in d['tournaments']}; leak=g-tg; sys.exit(1 if (leak or 'player_guid' in b or 'profile_guid' in b) else 0)"
if %errorlevel% neq 0 (
  echo [pub-upc] PRIVACY GATE FAILED - refusing to publish. Resolve by hand.
  exit /b 1
)

REM Fast-forward only; if diverged, skip this tick (graceful, never force).
git fetch origin main 1>nul 2>nul
git merge --ff-only origin/main 1>nul 2>nul
if %errorlevel% neq 0 (
  echo [pub-upc] local and origin/main diverged; skipping this tick.
  exit /b 0
)

git add web/upcoming.json
git commit -m "data: live upcoming.json refresh" 1>nul 2>nul
git push origin main
if %errorlevel% neq 0 (
  echo [pub-upc] push failed ^(offline?^); will retry next run.
  exit /b 0
)
echo [pub-upc] published upcoming.json.
endlocal
exit /b 0
```

- [ ] **Step 2: Register the scheduled task in `install-autostart.ps1`**

Open `windows/install-autostart.ps1`, find the block that registers the redeploy task (search for `redeploy`). Immediately after it, add an analogous registration for the publish task running every 5 minutes. Match the existing script's style (same `Register-ScheduledTask`/`schtasks` approach it already uses); name it `BadmintonPublishUpcoming`, action = run `windows\publish-upcoming.bat`, trigger = every 5 minutes, run whether-or-not logged on. (Read the existing redeploy block and copy its exact registration idiom — do not invent a different one.)

- [ ] **Step 3: Verify the .bat parses (dry, on host) — optional in agent env**

The privacy-gate line is the only nontrivial part; verify it in isolation:
```bash
~/.local/bin/uv.exe run python -c "import json,re,sys; b=open('web/upcoming.json',encoding='utf-8').read(); d=json.loads(b); g=set(re.findall(r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}',b)); tg={t.get('tournament_guid') for t in d['tournaments']}; leak=g-tg; print('exit', 1 if (leak or 'player_guid' in b or 'profile_guid' in b) else 0)"
```
Expected: `exit 0` (the regenerated file from Task 4 has only the tournament GUID).

- [ ] **Step 4: Commit**

```bash
git add windows/publish-upcoming.bat windows/install-autostart.ps1
git commit -m "feat: unattended scheduled task to publish live upcoming.json (graceful)"
```

---

### Task 10: Docs — clarify the privacy rule + verification

**Files:**
- Modify: `CLAUDE.md` (rule #4 one-line clarification)
- Verify: `/api/health` + manual view check

**Interfaces:** none (docs + manual verification).

- [ ] **Step 1: Clarify rule #4 in `CLAUDE.md`**

In `CLAUDE.md` rule #4, append one sentence to the bullet about the publishable artifact:

```markdown
   - The *tournament* GUID is a public event identifier and MAY appear in
     `web/upcoming.json` (it is the tournament's own page id and powers the
     "open on tournamentsoftware" link). Player/profile GUIDs must NEVER appear.
```

- [ ] **Step 2: Start the server and health-check**

Run:
```bash
PYTHONUTF8=1 ~/.local/bin/uv.exe run badminton server --port 8000 &
sleep 4 && curl -fs http://localhost:8000/api/health && echo " HEALTH-OK"
```
Expected: a JSON health body then ` HEALTH-OK`.

- [ ] **Step 3: Manually verify the Upcoming view**

Open `http://localhost:8000/#/upcoming` (use the dev-browser skill or a screenshot). Confirm:
- the "next match" block shows one row per friend with time · round · vs opponent · event,
- the "open on tournamentsoftware →" link points at `…/tournament/1A563200-…/`,
- "updated N ago" renders.
Capture a screenshot as evidence (CLAUDE.md rule #6). Stop the server afterward.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: clarify tournament GUID is public in upcoming.json"
```

---

## Self-Review

**Spec coverage:**
- A (cadence) → Task 1. B2 (resilience: cookie mount + no crash-loop) → Tasks 2 & 8. B (Stadin GUID) → Task 8. C (host publish task, graceful/ff-only) → Task 9. D (GUID narrowing + tests) → Task 3. E (next-match block + link) → Tasks 5 & 6. F (browser poll) → Task 7. Data regen → Task 4. Privacy-rule doc → Task 10. Manual verification → Task 10. All spec sections map to a task.
- `redeploy.bat` non-wedge interaction → Task 9 (ff-only + skip).

**Placeholder scan:** No TBD/TODO/"handle edge cases". The one place that defers to the existing file's idiom (Task 9 Step 2, matching the redeploy registration style) is necessary because `install-autostart.ps1` was not read into this plan; the step names the exact task name, action, trigger, and instructs copying the established idiom.

**Type consistency:** `next_match_per_player` (Python, Task 5) and `nextMatchPerPlayer` (JS, Task 6) return the same row shape (`tournament`, `tournament_guid`, `player`, `event`, `node`) with the same ordering (time then player). `_GUID_KEYS` (Task 3) and the privacy-gate one-liners (Tasks 4 & 9) agree: keep `tournament_guid`, forbid `player_guid`/`profile_guid`/other GUIDs. Cadence constants `FIVE_MIN=300`/`TEN_MIN=600` (Task 1) are the values asserted in its tests.

## Execution

Per the repo owner's standing instruction, this plan is executed in a **fresh session** via `superpowers:subagent-driven-development` (one subagent per task + two-stage review). Do not execute inline.

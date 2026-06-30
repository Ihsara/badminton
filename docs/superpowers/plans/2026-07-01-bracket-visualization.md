# Tournament Bracket Visualization (sub-project B) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **READ FIRST — Task 1 is a brainstorming session with the human.** Per the
> user's decision, the visual design is NOT locked. Do Task 1 (brainstorming)
> with the user before building Tasks 2+. The look/interaction details in later
> tasks are a STARTING POINT that Task 1 may revise — update the plan if so.

**Goal:** A private, password-gated "Archive" view in the home-server web app that renders a tournament's draws as visual brackets (rounds left→right, match boxes with player slots, winner highlighted, scores) — reading the already-shipped `/api/archive/*` endpoints from sub-project A.

**Architecture:** Pure frontend addition to the existing zero-build static explorer (`web/`). A new authed view (modeled on the existing `maintain.js` password-gated Maintain tab) fetches `GET /api/archive/tournaments` and `GET /api/archive/tournament/{id}/bracket`, then lays out brackets from the stored `round_index` / `position` / `side*_player_ids` / `winner_side` / `score_raw` fields. NO backend changes — A already exposes everything. NO change to the public `data.json` / `upcoming.json` pipeline.

**Tech Stack:** Vanilla JS (the explorer is zero-build, no framework), HTML, CSS. FastAPI server (`server.py`) already serves `web/` statically and exposes the archive endpoints. `pytest` for the one backend-shape test; manual + dev-browser verification for the UI.

## Global Constraints

- **PRIVACY IS THE ARCHITECTURE (rule #4).** The archive holds profile GUIDs and full rosters. The bracket view is PRIVATE: it is gated behind the **edit password** (same posture as the Maintain tab) and is served only by the home server. NOTHING from the archive may be written into the public `web/data.json` / `web/upcoming.json` or committed to the public repo. The view fetches archive data at runtime via the authed API; it must never bake archive data into a committed file.
- **Public pipeline untouched.** `build.py` / `export.py` / `web/data.json` / `web/upcoming.json` stay byte-for-byte unaffected. This sub-project adds files and touches only the web explorer + (if needed) a thin server route for the page; it does not read the archive into the public snapshot.
- **uv only** for any Python (never bare `pip`/`python`); run via `uv run`. The agent shell may need the full path `~/.local/bin/uv.exe`.
- **ruff clean** for any Python touched: `uv run ruff check` must pass.
- **Reuse A's contract, don't re-derive topology.** `matches.round_index` (0 = final, ascending toward earlier rounds) and `matches.position` (slot order within a round) are stored explicitly by A precisely so B lays out the tree without recomputing it. Use them.
- **Auth uses the existing helper.** Password check reuses the server's `_check_password` / `EDIT_PASSWORD` posture; the frontend reuses the same password-entry pattern as `maintain.js` (do not invent a new auth scheme).
- **Verify, don't assert (rule #6).** Before claiming the view works, load it in a browser against a seeded archive DB and show a rendered bracket (screenshot via the dev-browser skill). Evidence before success claims.

## Data available from sub-project A (already shipped — do NOT rebuild)

`GET /api/archive/tournaments?password=…` → `[{"id","name","year","start_date"}]` (year desc, name).

`GET /api/archive/tournament/{tid}/bracket?password=…` →
```json
{
  "tournament": {"id","name","year","start_date","end_date","location","region","category","source_url","fetched_at"},
  "draws": [
    {"id","tournament_id","name","draw_type","ordering",
     "matches": [
       {"id","draw_id","round_label","round_index","position",
        "side1_player_ids","side2_player_ids","score_raw","winner_side",
        "scheduled_iso","court"}
     ]}
  ]
}
```
- `round_index`: 0 = Final, 1 = Semi, 2 = Quarter, 3 = R16, 4 = R32, 5 = R64, 99 = unknown (group/round-robin).
- `position`: 0-based slot order within a round (the bracket y-order).
- `side1_player_ids` / `side2_player_ids`: JSON arrays of `players.id` (1 id = singles side, 2 ids = doubles side). **NOTE:** the endpoint currently returns these as JSON **strings** (stored as TEXT). The frontend must `JSON.parse` them. **Player display names are NOT in this payload yet** — see Task 2 (it adds a player-name lookup to the endpoint, the one small backend change in this plan).
- `winner_side`: 1 | 2 | null.
- `score_raw`: e.g. `"21-15 21-18"` or null (A defers real played-bracket scores; may be null for many matches — the view must render gracefully when null).

> **KNOWN DATA GAP (read before Task 1):** As of A's deployment the archive DB is
> **empty** — the live `/find/tournament` only exposes the upcoming window and its
> draw content is JS-lazy-loaded, so no finished brackets were captured. Therefore
> **B must be built and tested against a SEEDED fixture archive** (Task 3 seeds a
> realistic multi-round bracket into a temp DB), NOT against live data. Rendering
> real captured tournaments is gated on the historical-discovery follow-up
> (sub-project A's documented gap) and is out of scope here. B's job is: given the
> A schema populated, render it correctly.

## File Structure

| File | Responsibility |
|------|----------------|
| `web/archive.js` | New: the Archive view — password entry, tournament list fetch, bracket render, mount/teardown. The whole B frontend lives here. |
| `web/index.html` (modify) | Add the "Archive" nav entry + an empty `#archive` container the view mounts into. |
| `web/styles.css` (modify) | Bracket layout + match-box styling (rounds as columns, slots, winner highlight, score). |
| `src/badminton_tracker/server.py` (modify) | Tiny change: include player display names in the `/bracket` payload so the frontend can label slots (Task 2). |
| `tests/test_archive_endpoints.py` (modify) | Add a test asserting the bracket payload now carries player names. |

---

### Task 1: Brainstorming session — lock the bracket look & interactions (HUMAN-IN-LOOP)

**This task is a conversation with the user, not code.** Use the
`superpowers:brainstorming` skill. Do NOT write frontend code until the user has
confirmed the design here.

**Goal of the session:** turn "a bracket viz like badmintonfinland, but
friend-aware, on a private page" into concrete, buildable decisions.

- [ ] **Step 1: Run the brainstorming skill** with the user, covering at least:
  - **Layout:** classic left→right elimination tree (rounds as columns) — confirm. How to render group/round-robin draws (`round_index == 99`) — a standings table, a simple match list, or skip them in v1?
  - **Match box:** what each box shows — both player/pair names, winner highlight (which side won), score (`score_raw`), court/time (`scheduled_iso`)? What when `score_raw`/`winner_side` is null (unplayed/walkover)?
  - **Friend-awareness:** should the friend group's path be highlighted (e.g. bold/colored slots for core nicknames, like the existing "The Bros" tiering)? If yes, where does the friend list come from on a PRIVATE page (it MAY use real names/rosters since it's authed) — reuse the core-group list, or match against the private people/aliases?
  - **Navigation:** tournament picker (the `/tournaments` list) → draw picker (tabs per draw, e.g. "MS A", "WD") → bracket. Confirm this drill-down.
  - **Scope of v1:** smallest thing worth shipping — pick ONE draw type rendered well (elimination) and defer the rest.
  - **Empty/error states:** archive empty (current reality), wrong password, tournament has no draws.

- [ ] **Step 2: Write the decisions back into this plan.** Update Tasks 2–6 below to match what was decided (especially the match-box contents and friend-highlight rule). If the user picks something materially different (e.g. a non-tree layout), revise the affected tasks before proceeding. Commit the plan update:

```bash
git add docs/superpowers/plans/2026-07-01-bracket-visualization.md
git commit -m "docs(viz): lock bracket design decisions from brainstorming"
```

> Tasks 2–6 below are written against the DEFAULT assumption (classic elimination
> tree, match box = two slots + winner highlight + score, friend slots highlighted
> via the existing core-nickname list, drill-down nav). If Task 1 confirms these,
> proceed as written.

---

### Task 2: Add player display names to the bracket endpoint

The `/bracket` payload returns player-id arrays but no names, so the frontend
can't label slots. Add names server-side (one small, well-bounded change).

**Files:**
- Modify: `src/badminton_tracker/server.py` (the `archive_bracket` route)
- Test: `tests/test_archive_endpoints.py`

**Interfaces:**
- Consumes: `archive_db.connect`, the existing `players` table (`id`, `display_name`).
- Produces: each match in the `/bracket` response gains `side1` and `side2` — JSON arrays of `{"id","name"}` for the players on each side (alongside the existing raw `side1_player_ids`/`side2_player_ids`, which stay for back-compat). The frontend reads `side1`/`side2`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_archive_endpoints.py  (append)
def test_bracket_includes_player_names(tmp_path, monkeypatch):
    from badminton_tracker import config
    monkeypatch.setattr(config, "EDIT_PASSWORD", "secret")
    monkeypatch.setattr(config, "ARCHIVE_DB", tmp_path / "a.sqlite")
    import importlib
    from badminton_tracker import archive_db, server
    importlib.reload(server)
    conn = archive_db.connect(tmp_path / "a.sqlite")
    archive_db.upsert_tournament(conn, {
        "id": "T1", "name": "Cup", "year": 2024, "start_date": "2024-04-12",
        "end_date": "2024-04-12", "location": None, "region": None,
        "category": None, "source_url": None, "fetched_at": "t"})
    archive_db.upsert_draw(conn, {
        "id": "D1", "tournament_id": "T1", "name": "MS",
        "draw_type": "elimination", "ordering": 0})
    a = archive_db.upsert_player(conn, {"tournament_id": "T1",
        "display_name": "Alice Smith", "profile_guid": None, "club": None, "seed": None})
    b = archive_db.upsert_player(conn, {"tournament_id": "T1",
        "display_name": "Bob Jones", "profile_guid": None, "club": None, "seed": None})
    archive_db.insert_match(conn, {
        "draw_id": "D1", "round_label": "Final", "round_index": 0, "position": 0,
        "side1_player_ids": [a], "side2_player_ids": [b],
        "score_raw": "21-15 21-18", "winner_side": 1,
        "scheduled_iso": None, "court": None})
    conn.close()
    from fastapi.testclient import TestClient
    c = TestClient(server.app)
    r = c.get("/api/archive/tournament/T1/bracket", params={"password": "secret"})
    assert r.status_code == 200
    m = r.json()["draws"][0]["matches"][0]
    assert [p["name"] for p in m["side1"]] == ["Alice Smith"]
    assert [p["name"] for p in m["side2"]] == ["Bob Jones"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/bin/uv.exe run pytest tests/test_archive_endpoints.py::test_bracket_includes_player_names -v`
Expected: FAIL with `KeyError: 'side1'`.

- [ ] **Step 3: Add name resolution to `archive_bracket` in `server.py`**

In the `archive_bracket` route, after building each draw's `matches`, resolve the
player-id arrays to names. Add a small per-tournament id→name map and attach
`side1`/`side2` to each match dict. Minimal version:

```python
import json as _json  # at top of server.py if not already imported

# inside archive_bracket, after opening conn and confirming the tournament:
players = {r["id"]: r["display_name"] for r in conn.execute(
    "SELECT id, display_name FROM players WHERE tournament_id=?", (tid,)).fetchall()}

def _side(raw):
    ids = _json.loads(raw) if raw else []
    return [{"id": pid, "name": players.get(pid, "?")} for pid in ids]

# when assembling each match dict:
#   md = dict(m)
#   md["side1"] = _side(m["side1_player_ids"])
#   md["side2"] = _side(m["side2_player_ids"])
#   matches.append(md)
```

> Implementer: match the existing structure of `archive_bracket` (it already loops
> draws and builds `matches`). Insert the `side1`/`side2` attachment in that loop.
> Keep the raw `side1_player_ids`/`side2_player_ids` fields for back-compat (the
> existing endpoint test must still pass).

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/.local/bin/uv.exe run pytest tests/test_archive_endpoints.py -v`
Expected: PASS (the new test + the existing tournaments/auth tests).

- [ ] **Step 5: ruff + full suite + commit**

```bash
~/.local/bin/uv.exe run ruff check src/badminton_tracker/server.py tests/test_archive_endpoints.py
~/.local/bin/uv.exe run pytest -q
git add src/badminton_tracker/server.py tests/test_archive_endpoints.py
git commit -m "feat(viz): include player names in the bracket endpoint"
```

---

### Task 3: Seed a realistic fixture archive for manual + browser testing

B can't be tested against live data (archive is empty). Add a tiny dev helper that
seeds a temp archive DB with one multi-round elimination draw, so the view has
something real-shaped to render. This is a TEST/DEV artifact, not production code.

**Files:**
- Create: `tests/fixtures/archive/seed_demo.py` (a small script: build an in-memory-shaped sqlite at a given path with one tournament, one elimination draw, a Quarter→Semi→Final ladder with names, winners, scores).
- Test: none (it's a fixture generator); but add a `pytest` smoke test that runs it into `tmp_path` and asserts the bracket endpoint returns a 3-round structure.

**Interfaces:**
- Consumes: `archive_db` upsert helpers.
- Produces: `seed_demo(db_path)` — populates the DB; returns the tournament id.

- [ ] **Step 1: Write the failing smoke test**

```python
# tests/test_archive_viz_seed.py
from badminton_tracker import archive_db
from tests.fixtures.archive.seed_demo import seed_demo


def test_seed_demo_builds_multiround_bracket(tmp_path):
    db = tmp_path / "demo.sqlite"
    tid = seed_demo(db)
    conn = archive_db.connect(db)
    rounds = {r["round_index"] for r in conn.execute(
        "SELECT m.round_index FROM matches m "
        "JOIN draws d ON d.id=m.draw_id WHERE d.tournament_id=?", (tid,)).fetchall()}
    conn.close()
    assert {0, 1, 2} <= rounds  # Final, Semi, Quarter present
```

- [ ] **Step 2: Run to verify it fails**

Run: `~/.local/bin/uv.exe run pytest tests/test_archive_viz_seed.py -v`
Expected: FAIL (`ModuleNotFoundError` for `seed_demo`).

- [ ] **Step 3: Write `tests/fixtures/archive/seed_demo.py`**

```python
"""Dev/test seeder: one elimination draw with Quarter→Semi→Final, real-shaped
(names, winners, scores) so the bracket view has something to render. NOT prod."""
from __future__ import annotations

from pathlib import Path

from badminton_tracker import archive_db


def seed_demo(db_path: Path) -> str:
    conn = archive_db.connect(db_path)
    tid = "DEMO-T1"
    archive_db.upsert_tournament(conn, {
        "id": tid, "name": "Demo Open 2024", "year": 2024,
        "start_date": "2024-04-12", "end_date": "2024-04-13", "location": "Helsinki",
        "region": None, "category": None, "source_url": None, "fetched_at": "t"})
    archive_db.upsert_draw(conn, {
        "id": "D1", "tournament_id": tid, "name": "Men's Singles",
        "draw_type": "elimination", "ordering": 0})
    names = ["Alice Smith", "Bob Jones", "Cara Lee", "Dan Park",
             "Eve Kahn", "Finn Oja", "Gia Roy", "Hugo Vik"]
    pid = {n: archive_db.upsert_player(conn, {
        "tournament_id": tid, "display_name": n, "profile_guid": None,
        "club": None, "seed": None}) for n in names}

    def match(round_index, round_label, position, s1, s2, winner, score):
        archive_db.insert_match(conn, {
            "draw_id": "D1", "round_label": round_label, "round_index": round_index,
            "position": position, "side1_player_ids": [pid[s1]],
            "side2_player_ids": [pid[s2]], "score_raw": score,
            "winner_side": winner, "scheduled_iso": None, "court": None})

    # Quarter finals (round_index 2)
    match(2, "Quarter final", 0, "Alice Smith", "Bob Jones", 1, "21-15 21-18")
    match(2, "Quarter final", 1, "Cara Lee", "Dan Park", 2, "19-21 21-17 21-12")
    match(2, "Quarter final", 2, "Eve Kahn", "Finn Oja", 1, "21-9 21-14")
    match(2, "Quarter final", 3, "Gia Roy", "Hugo Vik", 2, "21-19 21-19")
    # Semi finals (round_index 1)
    match(1, "Semi final", 0, "Alice Smith", "Dan Park", 1, "21-16 21-13")
    match(1, "Semi final", 1, "Eve Kahn", "Hugo Vik", 2, "18-21 21-15 21-19")
    # Final (round_index 0)
    match(0, "Final", 0, "Alice Smith", "Hugo Vik", 1, "21-17 21-15")
    conn.commit()
    conn.close()
    return tid
```

- [ ] **Step 4: Run to verify it passes**

Run: `~/.local/bin/uv.exe run pytest tests/test_archive_viz_seed.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/archive/seed_demo.py tests/test_archive_viz_seed.py
git commit -m "test(viz): demo bracket seeder for the archive view"
```

---

### Task 4: Archive nav entry + view scaffold (password gate)

Add the "Archive" entry to the explorer and a view module that gates on the edit
password (modeled on `maintain.js`) and, once unlocked, fetches + lists tournaments.
No bracket rendering yet — just: enter password → see the tournament list (or the
empty-state message, since the real archive is empty).

**Files:**
- Modify: `web/index.html` (nav entry + `#archive` container)
- Create: `web/archive.js`
- Modify: `web/styles.css` (minimal: list + password form)

**Interfaces:**
- Consumes: `GET /api/archive/tournaments?password=…` (401 on wrong password).
- Produces: a global `initArchive()` (or matches the explorer's existing view-init convention — READ `app.js`/`maintain.js` first and follow whatever pattern they use: hash route, tab click handler, or explicit init). Renders into `#archive`.

> Implementer: `web/app.js` is binary-flagged (git can't diff it) but is plain JS —
> READ it to learn the view/tab/routing convention and the password-entry pattern in
> `maintain.js`, then mirror them. Do NOT invent a new pattern.

- [ ] **Step 1: Add the nav entry + container to `index.html`**

Add an "Archive" nav item alongside the existing ones and an empty mount point:

```html
<!-- in the nav -->
<a href="#archive" class="nav-link" data-view="archive">Archive</a>
<!-- in the views area -->
<section id="archive" class="view" hidden></section>
```
(Match the EXACT nav/view markup the explorer already uses — copy an existing entry and adapt.)

- [ ] **Step 2: Write `web/archive.js` — password gate + tournament list**

```javascript
// web/archive.js — PRIVATE archive view (edit-password gated). No archive data
// is ever persisted client-side or committed; everything is fetched at runtime.
(function () {
  const root = () => document.getElementById("archive");
  let password = sessionStorage.getItem("archivePw") || "";

  async function fetchTournaments() {
    const r = await fetch("/api/archive/tournaments?password=" + encodeURIComponent(password));
    if (r.status === 401 || r.status === 403) { password = ""; throw new Error("auth"); }
    return r.json();
  }

  function renderPasswordForm(msg) {
    root().innerHTML =
      '<form id="archPw" class="maintain-pw">' +
      (msg ? '<p class="err">' + msg + "</p>" : "") +
      '<input type="password" placeholder="Edit password" id="archPwInput">' +
      '<button>Unlock archive</button></form>';
    root().querySelector("#archPw").addEventListener("submit", (e) => {
      e.preventDefault();
      password = root().querySelector("#archPwInput").value;
      sessionStorage.setItem("archivePw", password);
      load();
    });
  }

  function renderList(tournaments) {
    if (!tournaments.length) {
      root().innerHTML = '<p class="muted">The archive is empty. Run ' +
        "<code>badminton archive-crawl</code> to populate it.</p>";
      return;
    }
    root().innerHTML =
      '<ul class="arch-list">' +
      tournaments.map((t) =>
        '<li><a href="#archive/' + encodeURIComponent(t.id) + '">' +
        (t.name || t.id) + " <span class=\"muted\">" + (t.year || "") +
        "</span></a></li>").join("") +
      "</ul>";
  }

  async function load() {
    if (!password) return renderPasswordForm();
    try {
      renderList(await fetchTournaments());
    } catch (e) {
      renderPasswordForm(e.message === "auth" ? "Wrong edit password." : "Error loading archive.");
    }
  }

  // Expose an init the explorer calls when the Archive view is shown.
  window.initArchive = load;
})();
```

> Implementer: wire `initArchive` into the explorer's view-switch the SAME way
> `maintain.js` is wired (e.g. called on tab activation / hash change). Include
> `archive.js` from `index.html` next to the other scripts.

- [ ] **Step 3: Manual verification (server + dev-browser)**

Start the server against a SEEDED archive so the list isn't empty:

```bash
# seed a demo DB at the configured ARCHIVE_DB, then run the server
~/.local/bin/uv.exe run python -c "from pathlib import Path; from badminton_tracker import config; from tests.fixtures.archive.seed_demo import seed_demo; seed_demo(config.ARCHIVE_DB); print('seeded', config.ARCHIVE_DB)"
~/.local/bin/uv.exe run badminton server  # or the project's serve command
```

Use the **dev-browser skill**: open the app, click "Archive", enter the edit
password, confirm the "Demo Open 2024" tournament appears (and that a wrong
password shows "Wrong edit password."). Screenshot it.

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/archive.js web/styles.css
git commit -m "feat(viz): private Archive view — password gate + tournament list"
```

---

### Task 5: Render the bracket tree for a selected draw

Clicking a tournament fetches its `/bracket` payload and renders each elimination
draw as a left→right tree: one column per round (ordered by `round_index`
descending so earliest rounds are leftmost, Final rightmost), match boxes ordered
by `position`, each box showing both sides' names, the winner highlighted, and the
score.

**Files:**
- Modify: `web/archive.js` (add bracket fetch + render)
- Modify: `web/styles.css` (bracket columns, match box, winner highlight)

**Interfaces:**
- Consumes: `GET /api/archive/tournament/{id}/bracket?password=…` → payload from Task 2 (matches carry `side1`/`side2` name arrays, `winner_side`, `score_raw`, `round_index`, `position`).
- Produces: a `renderBracket(payload)` that draws all `draws` (one bracket per elimination draw; `round_index == 99` group draws rendered as a simple match list per the Task-1 decision).

- [ ] **Step 1: Add bracket rendering to `archive.js`**

```javascript
// add inside the IIFE in web/archive.js

async function fetchBracket(tid) {
  const r = await fetch("/api/archive/tournament/" + encodeURIComponent(tid) +
    "/bracket?password=" + encodeURIComponent(password));
  if (r.status === 401 || r.status === 403) { password = ""; throw new Error("auth"); }
  if (r.status === 404) throw new Error("notfound");
  return r.json();
}

function side(slot, isWinner) {
  const names = (slot || []).map((p) => p.name).join(" / ") || "—";
  return '<div class="slot' + (isWinner ? " slot--won" : "") + '">' + names + "</div>";
}

function matchBox(m) {
  return '<div class="match">' +
    side(m.side1, m.winner_side === 1) +
    side(m.side2, m.winner_side === 2) +
    '<div class="match__score">' + (m.score_raw || "") + "</div></div>";
}

function renderDraw(draw) {
  const elimination = draw.matches.some((m) => m.round_index !== 99);
  if (!elimination) {
    // group/round-robin: simple match list (per Task-1 decision)
    return '<div class="draw"><h3>' + draw.name + "</h3>" +
      draw.matches.map(matchBox).join("") + "</div>";
  }
  // group matches by round_index; columns ordered earliest→Final (desc index → leftmost)
  const byRound = {};
  draw.matches.forEach((m) => { (byRound[m.round_index] ||= []).push(m); });
  const indices = Object.keys(byRound).map(Number).sort((a, b) => b - a); // big→0
  const cols = indices.map((idx) => {
    const ms = byRound[idx].sort((a, b) => a.position - b.position);
    const label = ms[0].round_label || ("Round " + idx);
    return '<div class="round"><div class="round__title">' + label + "</div>" +
      ms.map(matchBox).join("") + "</div>";
  }).join("");
  return '<div class="draw"><h3>' + draw.name + '</h3><div class="bracket">' + cols + "</div></div>";
}

async function showTournament(tid) {
  try {
    const payload = await fetchBracket(tid);
    root().innerHTML = '<a href="#archive" class="back">← all tournaments</a>' +
      "<h2>" + (payload.tournament.name || tid) + "</h2>" +
      payload.draws.map(renderDraw).join("");
  } catch (e) {
    if (e.message === "auth") return renderPasswordForm("Wrong edit password.");
    root().innerHTML = '<a href="#archive" class="back">← back</a><p class="err">' +
      (e.message === "notfound" ? "Tournament not found." : "Error loading bracket.") + "</p>";
  }
}
```

- [ ] **Step 2: Route `#archive/{id}` to `showTournament`**

In the explorer's hash/route handling (or in `initArchive`), parse a
`#archive/{id}` hash and call `showTournament(id)`; bare `#archive` calls `load()`.
Match the explorer's existing hash-routing approach.

- [ ] **Step 3: Bracket CSS in `styles.css`**

```css
.bracket { display: flex; gap: 2rem; align-items: stretch; overflow-x: auto; }
.round { display: flex; flex-direction: column; justify-content: space-around; gap: 1rem; min-width: 12rem; }
.round__title { font-weight: 600; opacity: .7; margin-bottom: .25rem; }
.match { border: 1px solid var(--border, #ccc); border-radius: 6px; overflow: hidden; }
.slot { padding: .35rem .6rem; border-bottom: 1px solid var(--border, #eee); }
.slot--won { font-weight: 700; background: var(--won-bg, #eafbea); }
.match__score { padding: .2rem .6rem; font-size: .8rem; opacity: .7; }
```
(Adapt variables/colours to the explorer's existing theme tokens.)

- [ ] **Step 4: Manual verification (dev-browser)**

With the seeded demo DB + server running (as in Task 4 Step 3), open Archive →
unlock → click "Demo Open 2024". Confirm: three columns (Quarter / Semi / Final),
winners bolded + highlighted, scores shown, Final on the right. Screenshot it.

- [ ] **Step 5: Commit**

```bash
git add web/archive.js web/styles.css
git commit -m "feat(viz): render elimination bracket tree for a draw"
```

---

### Task 6: Friend-path highlight + polish (per Task-1 decision)

Apply the friend-awareness chosen in Task 1 (default: highlight slots whose player
is in the core friend group), plus responsive/empty-state polish. ONLY build what
Task 1 confirmed; if friend-highlight was deferred, this task is just the polish.

**Files:**
- Modify: `web/archive.js`, `web/styles.css`

**Interfaces:**
- Consumes: a friend-name list. On this PRIVATE page you MAY use real names. Reuse the existing core-group nickname constant if it is reachable client-side, OR add a tiny authed endpoint that returns the friend display-name set. Decide in Task 1; the plan default is: match slot names (case-insensitive) against the core nickname list already used by the public "The Bros" tiering.

- [ ] **Step 1: Add friend highlight to slot rendering**

In `side(...)`, add a `slot--friend` class when any player name matches the friend
set (case-insensitive). Style `.slot--friend { color: var(--accent); }`. Keep it
distinct from `.slot--won` (a friend can lose).

- [ ] **Step 2: Empty/responsive polish**

- Horizontal scroll for wide brackets (already via `.bracket{overflow-x:auto}` — confirm on a narrow window).
- Group-draw (`round_index 99`) rendering matches the Task-1 decision.
- Confirm the empty-archive and wrong-password states still read well.

- [ ] **Step 3: Manual verification (dev-browser)**

Re-open the seeded demo (rename a demo player to a known core nickname first, or
add one), confirm the friend slot is visually distinct from a winner slot.
Screenshot the final view.

- [ ] **Step 4: Full suite + ruff + commit**

```bash
~/.local/bin/uv.exe run pytest -q   # backend tests still green
~/.local/bin/uv.exe run ruff check
git add web/archive.js web/styles.css
git commit -m "feat(viz): friend-path highlight + bracket polish"
```

---

### Task 7: Deploy + live-verify the private view

**Files:** none (deploy + verification).

- [ ] **Step 1: Rebuild + redeploy the home container**

```bash
docker compose up -d --build
```

- [ ] **Step 2: Health + view check (rule #6 — evidence before claims)**

- `curl -s http://localhost:8000/api/health` → 200.
- With the dev-browser skill: open the live app, go to Archive, unlock with the
  real edit password. Since the live archive is empty, confirm the **empty-state**
  message renders (not an error). To prove the renderer end-to-end, seed the demo
  into the live `ARCHIVE_DB` (or a temp one) and screenshot a rendered bracket.

- [ ] **Step 3: Privacy gate before any commit/push (rule #4)**

Confirm `git ls-files | grep -E 'data/|\.env'` is empty and that NO archive data
was baked into `web/data.json`/`web/upcoming.json`. Only then push (as **Ihsara**,
per rule #5) if integrating.

---

## Self-Review

**Spec coverage:** B's goal (private, authed bracket visualization reading A's `/api/archive/*`) maps to: brainstorm/lock design (T1), name-enrich the endpoint (T2), testable seed data given the empty live archive (T3), authed view + tournament list (T4), bracket tree render (T5), friend highlight + polish (T6), deploy + verify (T7). The privacy posture (authed, never baked into the public snapshot) is a Global Constraint enforced in T4/T5 (runtime fetch only) and re-checked in T7.

**Placeholder scan:** Tasks 2–5 carry real, runnable code (endpoint name-resolution, seeder, password-gated view, bracket render + CSS). Task 1 is intentionally a human brainstorming step (not code) — flagged at the top so the executor runs it with the user first. Tasks 4–6 note that `web/app.js` is binary-flagged and the explorer's exact view/route/auth convention must be READ from `app.js`/`maintain.js` and mirrored (rather than guessing markup) — this is a mandatory inspection step, not a placeholder.

**Type consistency:** T2 produces `side1`/`side2` = arrays of `{id,name}`; T5's `side(slot)` consumes `slot[].name` — consistent. `round_index` (0=Final ascending) and `position` from A's schema are used in T5's column ordering exactly as A stores them. `initArchive`/`showTournament`/`fetchBracket`/`renderDraw` names are consistent across T4–T6.

**Known dependency (flagged for the executor):** the live archive is EMPTY (A's historical-discovery gap), so B is built and tested against the T3 seed fixture. Rendering real captured tournaments is gated on the A follow-up and is out of scope here. B proves: given A's schema populated, the bracket renders correctly and privately.

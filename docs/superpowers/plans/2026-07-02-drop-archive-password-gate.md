# Drop Archive Password Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the in-app edit-password gate from the Archive **read** path (server GET routes + frontend), keeping the archive private by where it is served (home-server only) rather than by an in-app password. EDIT-endpoint auth is unchanged.

**Architecture:** Two files change. `server.py`: delete the `_check_password` call + unused `password` param from the three `/api/archive/*` GET routes (keep `_check_password` for the POST routes). `web/archive.js`: `viewArchive` renders the tournament list directly when `window.MAINT` is present; delete the password form / `archPass()` / sessionStorage stash / `"auth"` error paths; fetches drop `?password=`. The `window.MAINT`-absent public guard stays.

**Tech Stack:** Python 3 / FastAPI / Starlette `TestClient` (pytest), vanilla JS frontend, `uv` for all Python, `ruff` for lint.

## Global Constraints

- **uv-only:** run Python via `uv run …` (full path `~\.local\bin\uv.exe` if not on PATH). Never bare `pip`/`python`.
- **Lint:** `uv run ruff check` must be clean before claiming done.
- **TDD:** failing test first, then minimal implementation.
- **No `Co-Authored-By`** in any commit message.
- **Privacy (rule #4):** backend + private frontend only. Do NOT touch `web/data.json`, the public pipeline, or anything under `data/`. `git status --porcelain web/` must show only `web/archive.js` (plus the pre-existing unrelated `web/upcoming.json` change already in the tree — do NOT stage it).
- **EDIT auth untouched:** `POST /api/nicknames` and `POST /api/upload-excel` keep `_check_password`.
- **Public guard intact:** `web/archive.js`'s `!window.MAINT` → "Archive is off here" branch stays.

---

### Task 1: Server — make archive GET routes password-free (TDD)

**Files:**
- Modify: `src/badminton_tracker/server.py` (routes at ~132-166: `archive_tournaments`, `archive_core_names`, `archive_bracket`)
- Test: `tests/test_archive_endpoints.py`

**Interfaces:**
- Consumes: existing `_client(tmp_path, monkeypatch, password="secret")` helper in the test file (sets `EDIT_PASSWORD`, patches `ARCHIVE_DB`, seeds a `T1` tournament, reloads `server`, returns a `TestClient`). Keep it as-is.
- Produces: `GET /api/archive/tournaments`, `GET /api/archive/core-names`, `GET /api/archive/tournament/{tid}/bracket` all return 200 with **no** `password` query param. `POST /api/nicknames` still returns 401 without a password.

- [ ] **Step 1: Rewrite the test file to the new contract**

Replace the entire contents of `tests/test_archive_endpoints.py` with:

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


def test_tournaments_lists_without_password(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.get("/api/archive/tournaments")
    assert r.status_code == 200
    assert any(t["id"] == "T1" for t in r.json())


def test_bracket_includes_player_names_without_password(tmp_path, monkeypatch):
    from badminton_tracker import archive_db

    c = _client(tmp_path, monkeypatch)
    conn = archive_db.connect(tmp_path / "a.sqlite")
    archive_db.upsert_draw(conn, {
        "id": "D1", "tournament_id": "T1", "name": "MS",
        "draw_type": "elimination", "ordering": 0})
    a = archive_db.upsert_player(conn, {
        "tournament_id": "T1", "display_name": "Alice Smith",
        "profile_guid": None, "club": None, "seed": None})
    b = archive_db.upsert_player(conn, {
        "tournament_id": "T1", "display_name": "Bob Jones",
        "profile_guid": None, "club": None, "seed": None})
    archive_db.insert_match(conn, {
        "draw_id": "D1", "round_label": "Final", "round_index": 0, "position": 0,
        "side1_player_ids": [a], "side2_player_ids": [b],
        "score_raw": "21-15 21-18", "winner_side": 1,
        "scheduled_iso": None, "court": None})
    conn.close()

    r = c.get("/api/archive/tournament/T1/bracket")
    assert r.status_code == 200
    m = r.json()["draws"][0]["matches"][0]
    assert [p["name"] for p in m["side1"]] == ["Alice Smith"]
    assert [p["name"] for p in m["side2"]] == ["Bob Jones"]


def test_core_names_returns_core_set_without_password(tmp_path, monkeypatch):
    from badminton_tracker.core_group import CORE_NICKNAMES

    c = _client(tmp_path, monkeypatch)
    r = c.get("/api/archive/core-names")
    assert r.status_code == 200
    names = r.json()["names"]
    assert isinstance(names, list)
    assert "Chau" in names
    assert set(names) == set(CORE_NICKNAMES)


def test_edit_endpoint_still_requires_password(tmp_path, monkeypatch):
    # Mutation auth boundary is unchanged: no password -> 401/403.
    c = _client(tmp_path, monkeypatch)
    r = c.post("/api/nicknames", json={"rows": []})
    assert r.status_code in (401, 403)
```

- [ ] **Step 2: Run the tests to verify the GET tests fail**

Run: `uv run pytest tests/test_archive_endpoints.py -v`
Expected: the three `*_without_password` tests FAIL (currently return 401 because the routes still call `_check_password`). `test_edit_endpoint_still_requires_password` PASSES already.

- [ ] **Step 3: Drop the password from the three archive GET routes**

In `src/badminton_tracker/server.py`, edit the three GET route signatures + bodies so they no longer take or check a password.

`archive_tournaments`:
```python
@app.get("/api/archive/tournaments")
def archive_tournaments():
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
```

`archive_core_names`:
```python
@app.get("/api/archive/core-names")
def archive_core_names():
    return {"names": sorted(CORE_NICKNAMES)}
```

`archive_bracket` (only the signature + the removed `_check_password` line change; leave the rest of the body intact):
```python
@app.get("/api/archive/tournament/{tid}/bracket")
def archive_bracket(tid: str):
    from . import archive_db
    if not ARCHIVE_DB.exists():
        raise HTTPException(404, "Archive not built")
    conn = archive_db.connect(ARCHIVE_DB)
    try:
        t = conn.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
        ...
```

Do NOT remove `_check_password` or `_writes_enabled` — the POST routes still use them.

- [ ] **Step 4: Run the tests to verify all pass**

Run: `uv run pytest tests/test_archive_endpoints.py -v`
Expected: all four tests PASS.

- [ ] **Step 5: Lint**

Run: `uv run ruff check src/badminton_tracker/server.py tests/test_archive_endpoints.py`
Expected: clean (no unused-import / unused-arg warnings from the removed `password` params).

- [ ] **Step 6: Commit**

```bash
git add src/badminton_tracker/server.py tests/test_archive_endpoints.py
git commit -m "feat(archive): drop password from archive GET routes; keep edit auth"
```

---

### Task 2: Frontend — Archive opens straight to the tournament list

**Files:**
- Modify: `web/archive.js` (whole file — the password flow is threaded through several functions)

**Interfaces:**
- Consumes: `window.MAINT` (present only on the home server), `window.MAINT.base`, existing `esc`/`stagger` helpers, and the now-password-free `/api/archive/*` endpoints from Task 1.
- Produces: no password form; `viewArchive` → `renderArchiveList`. `archPass`, `renderArchivePasswordForm`, `loadArchive`, and the `archivePw` sessionStorage stash no longer exist.

> This is a pure-JS, zero-build frontend with no JS test harness — verification is manual (browser) at the end. Steps below are the exact edits.

- [ ] **Step 1: `viewArchive` — render the list directly, drop the password form**

Replace the `viewArchive` function (currently lines ~10-24) with:

```javascript
async function viewArchive(app, id, drawId) {
  if (!window.MAINT) {
    app.innerHTML = `<div class="empty rise" style="padding:64px">
      <h1 class="section-title" style="font-size:1.6rem">Archive is off here</h1><br>
      Browsing the archived brackets is only available on the home server
      (the always-on machine). This looks like the public snapshot.<br><br>
      <a class="tag" href="#/">← back to the group</a></div>`;
    return;
  }
  // #/archive/{id}/{drawId} -> one event sub-page; #/archive/{id} -> event index;
  // #/archive -> tournament list. No password: the home server is the boundary.
  if (id && drawId) { showArchiveDraw(id, drawId); return; }
  if (id) { showArchiveTournament(id); return; }
  const list = await fetchArchiveTournaments();
  if (list === null) {
    app.innerHTML = `
      <h1 class="section-title rise" style="margin:6px 0 4px;font-size:clamp(1.7rem,5vw,2.6rem)">Archive</h1>
      <div class="empty rise" style="padding:48px">
        Couldn't reach the archive on the home server.<br><br>
        <a class="tag" href="#/">← back to the group</a></div>`;
    stagger();
    return;
  }
  await ensureFriendSet();
  renderArchiveList(list);
}
```

- [ ] **Step 2: Delete `archPass` and update the module comment**

Delete the `archPass()` function (line ~26). In the top-of-file block comment, replace the sentence about the password kept in sessionStorage with:

```javascript
/* Archive panel: private list of archived tournaments, served ONLY by the
   always-on home server (window.MAINT). No archive data is ever persisted
   client-side or committed — everything is fetched at runtime from the
   container's /api/archive/* endpoints. Access is bounded by the home server
   being local/LAN-only, not by an in-app password. */
```

- [ ] **Step 3: `ensureFriendSet` — drop the `pw` param and the password query**

Replace `ensureFriendSet` (lines ~33-43) with:

```javascript
async function ensureFriendSet() {
  if (archFriendSet !== null) return;
  try {
    const r = await fetch(window.MAINT.base + "/api/archive/core-names");
    if (!r.ok) { archFriendSet = new Set(); return; }
    const data = await r.json();
    archFriendSet = new Set((data.names || []).map((n) => n.toLowerCase()));
  } catch (_) {
    archFriendSet = new Set();
  }
}
```

- [ ] **Step 4: Delete `renderArchivePasswordForm` and `loadArchive`**

Delete the entire `renderArchivePasswordForm` function (lines ~45-63) and the entire `loadArchive` function (lines ~65-74). They are now unused (`viewArchive` fetches the list directly; no unlock step).

- [ ] **Step 5: `fetchArchiveTournaments` — drop the password + auth path**

Replace `fetchArchiveTournaments` (lines ~76-85) with:

```javascript
async function fetchArchiveTournaments() {
  try {
    const r = await fetch(window.MAINT.base + "/api/archive/tournaments");
    if (!r.ok) return null;
    return await r.json();
  } catch (_) {
    return null;
  }
}
```

- [ ] **Step 6: `fetchArchiveBracket` — drop the password + auth path**

Replace `fetchArchiveBracket` (lines ~114-125) with:

```javascript
async function fetchArchiveBracket(id) {
  try {
    const r = await fetch(window.MAINT.base + "/api/archive/tournament/" +
      encodeURIComponent(id) + "/bracket");
    if (r.status === 404) return "notfound";
    if (!r.ok) return null;
    return await r.json();
  } catch (_) {
    return null;
  }
}
```

- [ ] **Step 7: `loadTournamentPayload` — drop the `pw` local**

Replace `loadTournamentPayload` (lines ~203-212) with:

```javascript
async function loadTournamentPayload(id) {
  if (archTournamentCache && archTournamentCache.id === id) {
    return archTournamentCache.payload;
  }
  await ensureFriendSet();
  const payload = await fetchArchiveBracket(id);
  if (payload && typeof payload === "object") archTournamentCache = { id, payload };
  return payload;
}
```

- [ ] **Step 8: `archBracketError` — remove the `"auth"` branch**

Replace `archBracketError` (lines ~214-225) with:

```javascript
function archBracketError(payload) {
  // Returns HTML for the non-object payloads, or "" when the payload is real.
  const back = `<a href="#/archive" class="tag rise">← all tournaments</a>`;
  if (payload === "notfound") {
    return back + `<div class="empty rise" style="padding:48px">Tournament not found.</div>`;
  }
  if (payload === null) {
    return back + `<div class="empty rise" style="padding:48px">Couldn't load the bracket.</div>`;
  }
  return ""; // real payload
}
```

Note: `showArchiveTournament`/`showArchiveDraw` call `archBracketError` and check `if (err === null) return;`. Since `archBracketError` no longer returns `null`, that early-return is now dead but harmless — leave those two call sites unchanged to keep the diff minimal.

- [ ] **Step 9: Grep to confirm no dangling password references**

Run: `grep -nE "archPass|archivePw|renderArchivePasswordForm|loadArchive|password=|\"auth\"" web/archive.js`
Expected: **no matches**. (If any appear, they are leftovers — remove them.)

- [ ] **Step 10: Commit**

```bash
git add web/archive.js
git commit -m "feat(archive): frontend opens archive without a password prompt"
```

---

### Task 3: Verify end-to-end (server + browser) and privacy

**Files:** none (verification only).

**Interfaces:** Consumes the running home server at `http://localhost:8000`.

- [ ] **Step 1: Full test suite green**

Run: `uv run pytest -q`
Expected: all tests pass (in particular `test_archive_endpoints.py` and the privacy tests `test_no_archive_import_in_public_pipeline`, `test_public_jsons_contain_no_profile_guids`).

- [ ] **Step 2: Lint clean**

Run: `uv run ruff check`
Expected: clean.

- [ ] **Step 3: Privacy / no-leak check**

Run: `git status --porcelain web/`
Expected: shows only `web/archive.js` as changed by this work (the pre-existing `web/upcoming.json` modification may also appear — it is NOT part of this work and must NOT be staged). Also run `git ls-files | grep -E 'data/|\.env'` → expected empty.

- [ ] **Step 4: Manual — home server opens archive with no prompt**

Rebuild/redeploy the container if needed (`windows\start.bat` = `docker compose up -d --build`), then confirm `GET http://localhost:8000/api/health` is 200. In a dev browser, open `http://localhost:8000/#/archive`:
- Expected: the tournament list renders immediately — **no password field, no unlock button**. Friend nicknames still highlight gold in brackets. Opening an event shows its bracket/standings.
- Confirm `GET http://localhost:8000/api/archive/tournaments` (no `?password=`) returns 200.

- [ ] **Step 5: Manual — public snapshot still hidden**

Open the archive route in a context where `window.MAINT` is absent (public snapshot / a build without the live container).
- Expected: still shows "Archive is off here". The public guard is intact.

- [ ] **Step 6 (optional): mark the source prompt done**

The originating prompt `context/prompts/archive-drop-password-gate.md` can be updated to `Status: DONE (main <hash>)` in a follow-up housekeeping commit, or left for the session-wrap step.

---

## Self-Review

**Spec coverage:**
- Server: remove `_check_password` from 3 GET routes → Task 1, Step 3. ✓
- Keep `_check_password` for POST routes → Task 1 Step 3 note + Task 1 Step 1 `test_edit_endpoint_still_requires_password`. ✓
- Frontend: viewArchive → list directly; delete form/archPass/stash; drop `?password=`; drop `"auth"` path → Task 2, all steps. ✓
- `window.MAINT` public guard stays → Task 2 Step 1 (branch preserved) + Task 3 Step 5. ✓
- Tests: remove `*_requires_password`, change to no-password 200, add EDIT-401 test → Task 1 Step 1. ✓
- Privacy tests stay green + no leak → Task 3 Steps 1, 3. ✓
- Manual verification (home + public) → Task 3 Steps 4-5. ✓

**Placeholder scan:** No TBD/TODO/"add error handling"/"similar to". All code shown verbatim. ✓

**Type/name consistency:** `fetchArchiveTournaments()`, `fetchArchiveBracket(id)`, `ensureFriendSet()`, `loadTournamentPayload(id)`, `archBracketError(payload)` — call sites updated to match new signatures (viewArchive, loadTournamentPayload). `_check_password`/`_writes_enabled` kept. Test helper `_client` signature unchanged. ✓

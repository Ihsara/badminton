# Player De-dup + Core-Group Tiering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the public site so each person appears exactly once (case/variant duplicates merged), and so the small core friend group is shown prominently while peripheral players are visually de-emphasised.

**Architecture:** Two independent concerns, both computed in the Python export so the published `web/data.json` is already correct (no client-side guessing):
1. **De-dup** — when several recorded spellings differ only by letter-case (e.g. `Paphon Kasemvudhi` / `Paphon KASEMVUDHI`), collapse them to one canonical display name before the roster is built. This is done in the alias layer so it also covers any future ALL-CAPS spelling the scraper introduces.
2. **Core-group tier** — a checked-in constant lists the core friend nicknames. Each player object in `data.json` gains a boolean `core`. The web UI renders core friends in a primary "The Bros" section and peripherals in a secondary, muted "Also played" section.

Spelling variants that are NOT just case differences (e.g. `Marja Tianen` vs `Marja TIAINEN`, or the `Matti` nickname vs `Yuki Matti Wada` full name) are out of scope for the automatic merge — they need explicit human alias decisions and are handled as a one-off data edit in Task 5, not by code.

**Tech Stack:** Python 3.13 (managed by `uv`), pytest, ruff; vanilla JS (`web/app.js`), CSS (`web/styles.css`). No new dependencies.

## Global Constraints

- **Python via `uv` only** — never bare `pip`/`python`. Run tests with `~/.local/bin/uv.exe run python -m pytest` (full path needed in the agent's non-interactive shell), lint with `~/.local/bin/uv.exe run ruff check`.
- **TDD** — failing test first, watch it fail, minimal code, watch it pass, commit.
- **PRIVACY IS THE ARCHITECTURE** — never `git add` anything under `data/`, `.env`, or `out/` to the public repo. The only publishable data artifact is the GUID-free `web/data.json`. The core-group list contains **display nicknames only** (already public in `data.json`), so it lives in a checked-in Python constant — NOT in `data/`.
- **All statistics computed in Python** — `stats.py` owns aggregation; the JS only renders.
- **Verify, don't assert** — regenerate `web/data.json` and confirm counts + no duplicate names before claiming done.
- Commit messages: no `Co-Authored-By` trailer (matches this repo's history).
- The web file `web/app.js` may be reported as binary by `grep` due to an embedded byte; edit it with the Edit tool using exact string matches (Read the surrounding lines first).

---

## File Structure

- `src/badminton_tracker/aliases.py` — gains `casefold_merge_map(names)` that, given all recorded names, returns a `name → canonical-display` map collapsing case-only variants. `alias_map()` composition unchanged for explicit aliases.
- `src/badminton_tracker/export.py` — `export_from_excel()` applies the case-fold merge when building `display_names`; `build_payload()` / a small helper tags each player object with `core`.
- `src/badminton_tracker/core_group.py` — **new**, holds the `CORE_NICKNAMES` constant (frozenset of display nicknames) and an `is_core(name)` helper. Public-safe (nicknames only).
- `web/app.js` — `viewPlayers()` and `viewGroup()` split the roster into core vs peripheral sections.
- `web/styles.css` — muted styling for the peripheral section.
- `tests/test_aliases.py` — **new or extended**, covers `casefold_merge_map`.
- `tests/test_export_core.py` — **new**, covers the `core` tagging end-to-end.
- `data/aliases.csv` — one-off manual edit for the non-case spelling variants (Task 5). Committed to the **private** `data/` repo only.

---

### Task 1: Case-fold merge map in the alias layer

**Files:**
- Modify: `src/badminton_tracker/aliases.py`
- Test: `tests/test_aliases.py` (create if absent)

**Interfaces:**
- Produces: `casefold_merge_map(names: list[str]) -> dict[str, str]` — input is every recorded name; output maps each name that has a case-only twin to a single canonical spelling. The canonical spelling is the variant **with the most lowercase letters** (proper-case beats ALL-CAPS), ties broken by first-seen order. Names with no twin are absent from the map (so callers fall through to the identity).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_aliases.py
from __future__ import annotations

from badminton_tracker.aliases import casefold_merge_map


def test_casefold_merge_collapses_allcaps_variant():
    names = ["Paphon Kasemvudhi", "Paphon KASEMVUDHI", "Maila"]
    m = casefold_merge_map(names)
    # Both Paphon spellings map to the proper-case one; Maila (no twin) is absent.
    assert m["Paphon KASEMVUDHI"] == "Paphon Kasemvudhi"
    assert m.get("Paphon Kasemvudhi") in (None, "Paphon Kasemvudhi")
    assert "Maila" not in m


def test_casefold_merge_prefers_more_lowercase_as_canonical():
    names = ["TUOMAS TIAINEN", "Tuomas Tiainen"]
    m = casefold_merge_map(names)
    assert m["TUOMAS TIAINEN"] == "Tuomas Tiainen"


def test_casefold_merge_no_twins_returns_empty():
    assert casefold_merge_map(["Maila", "Tong", "Junya"]) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/bin/uv.exe run python -m pytest tests/test_aliases.py -q`
Expected: FAIL with `ImportError` / `cannot import name 'casefold_merge_map'`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/badminton_tracker/aliases.py` (after `alias_map`):

```python
def casefold_merge_map(names: list[str]) -> dict[str, str]:
    """Map each name that differs from another only by letter-case to one
    canonical spelling, so case-only duplicates (e.g. "Paphon Kasemvudhi" and
    "Paphon KASEMVUDHI") collapse to a single person. The canonical spelling is
    the variant with the most lowercase letters (proper-case beats ALL-CAPS),
    ties broken by first appearance. Names with no case-twin are omitted."""
    groups: dict[str, list[str]] = {}
    for n in names:
        if not n:
            continue
        groups.setdefault(n.casefold(), [])
        if n not in groups[n.casefold()]:
            groups[n.casefold()].append(n)

    def _lower_count(s: str) -> int:
        return sum(1 for c in s if c.islower())

    out: dict[str, str] = {}
    for variants in groups.values():
        if len(variants) < 2:
            continue
        canonical = max(variants, key=lambda s: (_lower_count(s), -variants.index(s)))
        for v in variants:
            out[v] = canonical
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/bin/uv.exe run python -m pytest tests/test_aliases.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint + commit**

```bash
~/.local/bin/uv.exe run ruff check src/badminton_tracker/aliases.py tests/test_aliases.py
git add src/badminton_tracker/aliases.py tests/test_aliases.py
git commit -m "feat: casefold_merge_map collapses case-only name duplicates"
```

---

### Task 2: Apply the case-fold merge in export so duplicates disappear from data.json

**Files:**
- Modify: `src/badminton_tracker/export.py` (`apply_aliases` and `export_from_excel`)
- Test: `tests/test_export_core.py` (create)

**Interfaces:**
- Consumes: `casefold_merge_map` from Task 1; existing `aliases.apply`, `friend_names`, `read_data_matches`, `roster_from_names`, `export_json`.
- Produces: after `export_from_excel()`, the roster has one entry per person for case-only twins. `apply_aliases` now composes the explicit alias map with the case-fold map so names on the court collapse too.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_export_core.py
from __future__ import annotations

from badminton_tracker.export import apply_aliases


def test_apply_aliases_merges_case_only_duplicates():
    matches = [{
        "player_1": "Paphon Kasemvudhi", "player_2": "Paphon KASEMVUDHI",
        "opponent_1": "Maila", "opponent_2": "Tong",
    }]
    # No explicit alias rows; rely on the case-fold merge derived from the names.
    out = apply_aliases(matches, mapping={})
    names = {out[0]["player_1"], out[0]["player_2"]}
    assert names == {"Paphon Kasemvudhi"}  # both spellings collapsed to one
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/bin/uv.exe run python -m pytest tests/test_export_core.py -q`
Expected: FAIL — `names` is `{"Paphon Kasemvudhi", "Paphon KASEMVUDHI"}` (two entries), assertion fails.

- [ ] **Step 3: Write minimal implementation**

In `src/badminton_tracker/export.py`, update the import line and `apply_aliases`:

```python
from . import aliases
```
(already present — add the helper call below)

Replace the body of `apply_aliases` so it folds case-only twins built from the names actually present in `matches`:

```python
def apply_aliases(matches: list[dict], mapping: dict[str, str] | None = None) -> list[dict]:
    """Replace each recorded name with its chosen display nickname.

    The mapping is GUID-free — the private nickname→real-name→profile linkage
    never reaches data.json. Applied to every name on the court (friends and
    their opponents), so a relabel shows up everywhere. Case-only duplicates
    (e.g. "Paphon KASEMVUDHI") are folded to one canonical spelling first.
    """
    mapping = aliases.alias_map() if mapping is None else mapping
    all_names = [m[k] for m in matches
                 for k in ("player_1", "player_2", "opponent_1", "opponent_2")]
    casefold = aliases.casefold_merge_map(all_names)
    out = []
    for m in matches:
        mm = dict(m)
        for key in ("player_1", "player_2", "opponent_1", "opponent_2"):
            folded = casefold.get(m[key], m[key])
            mm[key] = aliases.apply(folded, mapping)
        out.append(mm)
    return out
```

Then in `export_from_excel`, fold the friend names before de-duplicating the roster so the two Paphon roster rows become one:

```python
def export_from_excel() -> None:
    """Build the public explorer data from the workbook, with nicknames applied.

    The roster (who gets a stats page / appears in standings) stays the friend
    group — the names on the Player 1/2 side of the log. The nickname editor is
    seeded with exactly that group, while aliases still display on every name.
    """
    friends = friend_names()
    aliases.ensure_names(friends)  # seed the editor with the group
    mapping = aliases.alias_map()
    matches = apply_aliases(read_data_matches(), mapping)
    # Fold case-only twins (e.g. "Paphon KASEMVUDHI") to one spelling, then apply
    # explicit aliases, so a person gets a single stats page — not one row per
    # spelling. Preserve order.
    casefold = aliases.casefold_merge_map(friends)
    display_names = list(dict.fromkeys(
        aliases.apply(casefold.get(f, f), mapping) for f in friends))
    roster = roster_from_names(display_names)
    export_json(matches, roster, source="excel")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/bin/uv.exe run python -m pytest tests/test_export_core.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `~/.local/bin/uv.exe run python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Lint + commit**

```bash
~/.local/bin/uv.exe run ruff check src/badminton_tracker/export.py tests/test_export_core.py
git add src/badminton_tracker/export.py tests/test_export_core.py
git commit -m "feat: fold case-only name duplicates in export (one stats page per person)"
```

---

### Task 3: Core-group constant + `core` flag on each player

**Files:**
- Create: `src/badminton_tracker/core_group.py`
- Modify: `src/badminton_tracker/export.py` (`build_payload` tags players)
- Test: `tests/test_export_core.py` (extend)

**Interfaces:**
- Produces: `core_group.CORE_NICKNAMES: frozenset[str]` and `core_group.is_core(name: str) -> bool` (case-insensitive match against the constant). Each object in `payload["players"]` gains `"core": bool`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_export_core.py`:

```python
from badminton_tracker.core_group import CORE_NICKNAMES, is_core
from badminton_tracker.export import build_payload
from badminton_tracker.export import roster_from_names


def test_core_membership_is_case_insensitive():
    assert is_core("Maila") is True
    assert is_core("maila") is True
    assert is_core("Paphon Kasemvudhi") is False


def test_core_group_has_expected_members():
    expected = {"Chau", "Dao", "Santeri", "Thy", "Maila",
                "Tong", "Junya", "Toni", "Matti", "Khai", "Boris"}
    assert {n for n in CORE_NICKNAMES} == expected


def test_build_payload_tags_core_flag():
    matches = [
        {"date": "2026-01-01", "tournament": "T", "category": "MD", "level": "B",
         "round": "R1", "player_1": "Maila", "player_2": "Paphon Kasemvudhi",
         "opponent_1": "X", "opponent_2": "Y",
         "team1": ["Maila", "Paphon Kasemvudhi"], "team2": ["X", "Y"],
         "sets": [[21, 10]]},
    ]
    roster = roster_from_names(["Maila", "Paphon Kasemvudhi"])
    payload = build_payload(matches, roster, source="test")
    by_name = {p["player"]: p for p in payload["players"]}
    assert by_name["Maila"]["core"] is True
    assert by_name["Paphon Kasemvudhi"]["core"] is False
```

> Note: `build_payload` calls `dedupe_matches` and `_match_payload`; the single match above must carry the fields those expect. If the test errors on a missing key, read `_match_payload`/`_canonical_key` in `export.py` and add the minimal missing keys to the fixture (do NOT change production code to accommodate the test).

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.local/bin/uv.exe run python -m pytest tests/test_export_core.py -q`
Expected: FAIL — `ModuleNotFoundError: badminton_tracker.core_group`.

- [ ] **Step 3: Write minimal implementation**

Create `src/badminton_tracker/core_group.py`:

```python
"""The core friend group — display nicknames only (public-safe).

These are the people whose stats page should be shown prominently on the site.
Everyone else who appears on the Player side of the log is "peripheral" (an
occasional partner, a coach, a one-off). Nicknames are already public in
data.json, so this list carries no private identity data and is checked into
the public repo.
"""

from __future__ import annotations

CORE_NICKNAMES: frozenset[str] = frozenset({
    "Chau", "Dao", "Santeri", "Thy", "Maila",
    "Tong", "Junya", "Toni", "Matti", "Khai", "Boris",
})

_CORE_FOLDED = {n.casefold() for n in CORE_NICKNAMES}


def is_core(name: str) -> bool:
    """Case-insensitive membership test against the core group."""
    return bool(name) and name.casefold() in _CORE_FOLDED
```

In `export.py`, import it and tag players inside `build_payload` (after `pstats` is computed):

```python
from .core_group import is_core
```

```python
    pstats = player_stats(deduped, roster)
    for p in pstats:
        p["core"] = is_core(p["player"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/.local/bin/uv.exe run python -m pytest tests/test_export_core.py -q`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
~/.local/bin/uv.exe run ruff check src/badminton_tracker/core_group.py src/badminton_tracker/export.py tests/test_export_core.py
git add src/badminton_tracker/core_group.py src/badminton_tracker/export.py tests/test_export_core.py
git commit -m "feat: tag each player with a core-group flag in data.json"
```

---

### Task 4: Render core vs peripheral tiers on the site

**Files:**
- Modify: `web/app.js` (`viewPlayers`, `viewGroup`)
- Modify: `web/styles.css`
- Test: manual (no JS test harness in repo) — verified live in Task 6.

**Interfaces:**
- Consumes: `p.core` boolean on each `DB.players` entry (Task 3).

- [ ] **Step 1: Update `viewPlayers` to split into two sections**

Read `web/app.js` around the current `viewPlayers` (≈ line 360) first, then replace it with:

```javascript
function viewPlayers() {
  const core = DB.players.filter((p) => p.core);
  const rest = DB.players.filter((p) => !p.core);
  const maxWins = Math.max(...DB.players.map((p) => p.wins), 1);
  const section = (title, list, muted) => list.length ? `
    <div class="block__head"><h2 class="section-title">${title}</h2></div>
    <div class="card lb ${muted ? "lb--muted" : ""}">${
      list.map((p, i) => lbRow(p, i, maxWins)).join("")}</div>` : "";
  app.innerHTML = `
    <div class="eyebrow rise">Roster</div>
    <h1 class="section-title rise" style="margin:8px 0 24px">All Players</h1>
    ${section("The Bros", core, false)}
    ${rest.length ? `<div style="height:18px"></div>` : ""}
    ${section("Also played", rest, true)}`;
  stagger();
}
```

- [ ] **Step 2: Update `viewGroup` standings to prefer core friends**

In `web/app.js` `viewGroup`, replace the `top` line so the home-page standings lead with the core group (falling back to fill 12 with peripherals if fewer than 12 core):

```javascript
  const c = DB.counts;
  const coreSorted = DB.players.filter((p) => p.core);
  const top = (coreSorted.length >= 12 ? coreSorted : [
    ...coreSorted, ...DB.players.filter((p) => !p.core)]).slice(0, 12);
```

- [ ] **Step 3: Add muted styling**

Read `web/styles.css` around the `.chip` / `.lb` rules first, then add near the leaderboard styles:

```css
.lb--muted { opacity:.62; }
.lb--muted .lb__row { filter:grayscale(.3); }
```

- [ ] **Step 4: Syntax-check the JS**

Run: `node --check web/app.js`
Expected: no output (exit 0).

- [ ] **Step 5: Commit**

```bash
git add web/app.js web/styles.css
git commit -m "feat: show core friends prominently, peripherals in a muted section"
```

---

### Task 5: One-off data edit for non-case spelling duplicates (private data repo)

**Files:**
- Modify: `data/aliases.csv` (PRIVATE — committed to the `data/` repo only, never the public repo)

**Context:** Task 1's code only merges case-only twins. Real spelling variants remain and need a human decision via the `display` column. Known clusters from the current `data.json` (verify against the live data before editing):
- `Marja TIAINEN` / `Marja Tianen` (misspelling, not just case) → choose one display, e.g. `Marja Tiainen`.
- `Matti` / `Yuki Matti Wada` / `Matti Yuki WADA` → all → `Matti` (memory: "Matti" = Yuki Matti).
- `Tommi Ruoho` / `Tommi Heinisaari` — DIFFERENT people (both 10g, 10w) — do NOT merge; confirm before touching.

- [ ] **Step 1: Inspect current duplicate clusters**

Run:
```bash
PYTHONIOENCODING=utf-8 ~/.local/bin/uv.exe run python -c "import json;d=json.load(open('web/data.json',encoding='utf-8'));[print(p['player'],p['games'],p['wins']) for p in sorted(d['players'],key=lambda x:-x['games'])]"
```
Identify rows that are the same person under different spelling (not case — those are already merged by Task 2).

- [ ] **Step 2: Edit `data/aliases.csv`**

For each confirmed same-person spelling cluster, set the `display` column of every variant to the single chosen display name. Example rows:
```
Marja TIAINEN,Marja Tiainen,
Marja Tianen,Marja Tiainen,
Yuki Matti Wada,Matti,
Matti Yuki WADA,Matti,
```
Leave genuinely different people untouched.

- [ ] **Step 3: Commit to the PRIVATE data repo only**

```bash
git -C data add aliases.csv
git -C data commit -m "data: merge non-case spelling duplicates to one display name"
```
Do NOT `git add data/aliases.csv` in the public repo.

---

### Task 6: Regenerate, verify privacy + no duplicates, redeploy live

**Files:** none (build + verification only).

- [ ] **Step 1: Regenerate `web/data.json` from the workbook**

Run: `~/.local/bin/uv.exe run badminton export`
(If the CLI subcommand differs, use the export entrypoint: `~/.local/bin/uv.exe run python -m badminton_tracker.export`.)
Expected: prints match/player/tournament counts; player count drops by the number of merged duplicates.

- [ ] **Step 2: Assert no duplicate display names remain**

Run:
```bash
PYTHONIOENCODING=utf-8 ~/.local/bin/uv.exe run python -c "import json;d=json.load(open('web/data.json',encoding='utf-8'));ns=[p['player'] for p in d['players']];import collections;dupes=[n for n,c in collections.Counter(n.casefold() for n in ns).items() if c>1];print('CASE-DUPES:',dupes);assert not dupes,'still duplicated'"
```
Expected: `CASE-DUPES: []`.

- [ ] **Step 3: Privacy gate — no profile GUIDs in data.json, no private files staged**

Run:
```bash
grep -ocE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' web/data.json
git ls-files | grep -E 'data/|\.env$'
```
Expected: first command prints `0`; second prints nothing.

- [ ] **Step 4: Confirm core flag present and correct count**

Run:
```bash
PYTHONIOENCODING=utf-8 ~/.local/bin/uv.exe run python -c "import json;d=json.load(open('web/data.json',encoding='utf-8'));core=[p['player'] for p in d['players'] if p.get('core')];print('CORE:',sorted(core))"
```
Expected: the core members that actually have logged games (subset of the 11).

- [ ] **Step 5: Commit the regenerated public artifact**

```bash
git add web/data.json
git commit -m "data: regenerate data.json (deduped players + core flag)"
```

- [ ] **Step 6: Open PR, squash-merge to main (Ihsara identity)**

```bash
gh auth status   # confirm "Active account: true" is Ihsara before pushing
git push -u origin <branch>
gh pr create --title "Player de-dup + core-group tiering" --body "..."
gh pr merge <n> --squash --delete-branch
```

- [ ] **Step 7: Redeploy + verify live**

```bash
docker compose up -d --build
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/health   # expect 200
```
Then load `http://localhost:8000/#/players` in the dev-browser and confirm: one Paphon row, core friends under "The Bros", peripherals under a muted "Also played". Screenshot as evidence.

---

## Self-Review

**Spec coverage:**
- Duplicate Paphon (and case twins) → Tasks 1, 2, 6. ✓
- Non-case spelling duplicates (Marja, Matti) → Task 5 (data edit). ✓
- Core group shown prominently, peripherals de-emphasised → Tasks 3, 4. ✓
- Core list = {Chau, Dao, Santeri, Thy, Maila, Tong, Junya, Toni, Matti, Khai, Boris} → Task 3 constant. ✓
- Public/privacy safety → Task 6 gates; core list is nickname-only constant, not in `data/`. ✓

**Placeholder scan:** PR body in Task 6 Step 6 left as `"..."` — intentional (author writes a real body at execution; not a code placeholder). All code steps carry full code.

**Type consistency:** `casefold_merge_map(list[str]) -> dict[str,str]` used identically in Tasks 1/2. `is_core(str) -> bool` and `CORE_NICKNAMES: frozenset[str]` consistent across Task 3 and Task 4 (JS reads the resulting `p.core` bool). `apply_aliases(matches, mapping={})` signature unchanged.

**Open risk:** Task 3's `build_payload` test fixture must satisfy `_match_payload`/`dedupe_matches`. The task note tells the implementer to read those and extend the fixture (not prod code) if a key is missing — acceptable, flagged.

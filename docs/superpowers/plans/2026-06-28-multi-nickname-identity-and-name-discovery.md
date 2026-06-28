# Multi-nickname Identity + Name-Based Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a person-centric identity model so one friend can be tracked across many nicknames/GUIDs (Chau / Long Chau Tran / eyyy), and a name-based discovery flow that finds GUID-less friends (e.g. Dao) by scanning confirmed friends' match pages and explicitly-chosen tournament participant lists, with a human-confirmed review queue.

**Architecture:** Two new **private** CSVs in `data/` (`people.csv` = one row per person; `person_aliases.csv` = many names/GUIDs per person), loaded by a new pure `identity.py` module. Discovery harvests names into a review queue (`discovery_candidates.csv`); nothing auto-links a name to a person. Four new CLI verbs (`identity-seed`, `discover-names`, `identity-confirm`). All scraping reuses the existing Playwright client + cookie-wall login. The public `web/*.json` is unchanged and never sees `person_id` or GUIDs; an automated privacy-guard test enforces that.

**Tech Stack:** Python (managed via `uv` — never bare `pip`/`python`), `csv`/`unicodedata` stdlib, `pytest`, Playwright (existing `client.py`), `ruff` for lint.

## Global Constraints

- **Python only via `uv`** — `uv sync`, `uv add`, `uv run`. Never bare `pip`/`python`. (CLAUDE.md rule #1)
- **Lint clean:** `uv run ruff check` must pass before any task is "done". (rule #2)
- **PRIVACY IS THE ARCHITECTURE (rule #4):** `data/people.csv`, `data/person_aliases.csv`, `data/discovery_candidates.csv` are PRIVATE — they live only in the nested `data/` repo and must be gitignored by the public repo. No `profile_guid`, no `person_id` may ever appear in `web/data.json` or `web/upcoming.json`.
- **Two repos (rule #5):** code → public `Ihsara/badminton`; data files → private `data/` repo via `versioning.commit(...)`.
- **Every data change is a commit in the private `data/` repo (rule #7).** Use `badminton_tracker.versioning.commit(paths, message, who="identity")`.
- **Verify, don't assert (rule #6):** run commands and read output before claiming success. A prior subagent falsely reported passing tests — re-run `uv run pytest` and read the actual output.
- **Scraper env-shadow gotcha:** empty `TOURNAMENTSOFTWARE_*` shell vars shadow `.env`. Any live scrape command must be prefixed with `unset TOURNAMENTSOFTWARE_USERNAME TOURNAMENTSOFTWARE_PASSWORD TOURNAMENTSOFTWARE_BASE_URL && ...`.
- **Existing files untouched:** `players.csv` / `load_players()` keep working; `aliases.csv` (public display) is unchanged this iteration.
- **Identity is exact, case-insensitive** name matching — NO fuzzy/token auto-linking (that produced the wrong "Dao = Quinn Dao" mapping).

---

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `src/badminton_tracker/config.py` | Add path constants `PEOPLE_CSV`, `PERSON_ALIASES_CSV`, `DISCOVERY_CANDIDATES_CSV` | 1 |
| `src/badminton_tracker/identity.py` | NEW. Pure loaders/writers + lookups over people.csv & person_aliases.csv | 2 |
| `src/badminton_tracker/identity_seed.py` | NEW. One-time migration: players.csv → people.csv + person_aliases.csv | 3 |
| `src/badminton_tracker/discovery_queue.py` | NEW. Pure read/write/fold of discovery_candidates.csv; harvest helper | 4, 5 |
| `src/badminton_tracker/discover_names.py` | NEW. Playwright drivers: Source A (friends) + Source B (participant lists). `# pragma: no cover` | 6 |
| `src/badminton_tracker/__main__.py` | Add `identity-seed`, `discover-names`, `identity-confirm` verbs | 3, 5, 6 |
| `.gitignore` (public repo root) | Gitignore the three new private CSVs | 1 |
| `tests/test_identity.py` | identity.py lookups + round-trip | 2 |
| `tests/test_identity_seed.py` | seed migration | 3 |
| `tests/test_discovery_queue.py` | harvest split + confirm fold | 4, 5 |
| `tests/test_privacy_guards.py` | no GUID/person_id in web/*.json | 7 |

**Task dependency order:** 1 → 2 → 3 → 4 → 5 → 6 → 7. Tasks 2–5 are pure (unit-tested); Task 6 is the live Playwright driver (manual verification); Task 7 is the privacy guard.

---

### Task 1: Config paths + gitignore the private files

**Files:**
- Modify: `src/badminton_tracker/config.py` (after line 30, the `MATCHES_MIRROR_CSV` block)
- Modify: `.gitignore` (public repo root)

**Interfaces:**
- Produces: `PEOPLE_CSV`, `PERSON_ALIASES_CSV`, `DISCOVERY_CANDIDATES_CSV` (all `pathlib.Path` under `DATA_DIR`).

- [ ] **Step 1: Add path constants to config.py**

Insert after the `MATCHES_MIRROR_CSV = DATA_DIR / "matches_mirror.csv"` line:

```python
# ── Identity model (PRIVATE — never published; gitignored by the public repo) ──
# One row per person (person_id, real_name, has_profile, notes):
PEOPLE_CSV = DATA_DIR / "people.csv"
# Many rows: every nickname/realname/GUID a person is known by:
PERSON_ALIASES_CSV = DATA_DIR / "person_aliases.csv"
# Name-based discovery review queue (human confirms each before it joins identity):
DISCOVERY_CANDIDATES_CSV = DATA_DIR / "discovery_candidates.csv"
```

- [ ] **Step 2: Gitignore the private files in the public repo**

Check the current `.gitignore` first: `grep -n "data/" .gitignore`. The `data/` directory is already gitignored as a whole (it's the nested repo), but add explicit belt-and-suspenders entries so the intent is documented. Append to `.gitignore`:

```gitignore
# Private identity model — lives only in the nested data/ repo (rule #4)
data/people.csv
data/person_aliases.csv
data/discovery_candidates.csv
```

- [ ] **Step 3: Verify the constants import cleanly**

Run: `uv run python -c "from badminton_tracker.config import PEOPLE_CSV, PERSON_ALIASES_CSV, DISCOVERY_CANDIDATES_CSV; print(PEOPLE_CSV.name, PERSON_ALIASES_CSV.name, DISCOVERY_CANDIDATES_CSV.name)"`
Expected: `people.csv person_aliases.csv discovery_candidates.csv`

- [ ] **Step 4: Lint + commit (public repo)**

```bash
uv run ruff check
git add src/badminton_tracker/config.py .gitignore
git commit -m "Add identity-model path constants + gitignore private CSVs"
```

---

### Task 2: identity.py — load/lookup/write the identity model

**Files:**
- Create: `src/badminton_tracker/identity.py`
- Test: `tests/test_identity.py`

**Interfaces:**
- Consumes: `config.PEOPLE_CSV`, `config.PERSON_ALIASES_CSV`.
- Produces:
  - `PEOPLE_FIELDS = ["person_id", "real_name", "has_profile", "notes"]`
  - `ALIAS_FIELDS = ["person_id", "alias", "kind", "guid", "source_tournament", "confidence"]`
  - `load_people(path=None) -> list[dict]` (keys = PEOPLE_FIELDS)
  - `load_person_aliases(path=None) -> list[dict]` (keys = ALIAS_FIELDS)
  - `write_people(rows, path=None) -> None`, `write_person_aliases(rows, path=None) -> None`
  - `person_for_name(name, aliases=None) -> str | None` — exact, case-insensitive alias match → person_id
  - `aliases_for_person(person_id, aliases=None) -> list[dict]`
  - `known_alias_names(aliases=None) -> set[str]` — lowercased set of every alias text

- [ ] **Step 1: Write the failing tests**

Create `tests/test_identity.py`:

```python
# tests/test_identity.py
from __future__ import annotations

from badminton_tracker import identity


def _seed(tmp_path):
    people = tmp_path / "people.csv"
    aliases = tmp_path / "person_aliases.csv"
    identity.write_people(
        [
            {"person_id": "p001", "real_name": "Long Chau Tran", "has_profile": "y", "notes": "me"},
            {"person_id": "p002", "real_name": "Chompoonooch Unwong", "has_profile": "n", "notes": "Dao"},
        ],
        path=people,
    )
    identity.write_person_aliases(
        [
            {"person_id": "p001", "alias": "Chau", "kind": "nickname", "guid": "",
             "source_tournament": "", "confidence": "high"},
            {"person_id": "p001", "alias": "Long Chau Tran", "kind": "realname",
             "guid": "d69f71b9-69f2-472e-97b2-4fc80ac43a17", "source_tournament": "", "confidence": "high"},
            {"person_id": "p001", "alias": "eyyy", "kind": "nickname", "guid": "",
             "source_tournament": "Kaarina May 2026", "confidence": "confirmed"},
            {"person_id": "p002", "alias": "Dao", "kind": "nickname", "guid": "",
             "source_tournament": "", "confidence": "high"},
        ],
        path=aliases,
    )
    return people, aliases


def test_round_trip_people(tmp_path):
    people, _ = _seed(tmp_path)
    rows = identity.load_people(path=people)
    assert len(rows) == 2
    assert rows[0]["person_id"] == "p001"
    assert rows[1]["has_profile"] == "n"  # GUID-less person is first-class


def test_person_for_name_is_case_insensitive_and_multi_nickname(tmp_path):
    _, aliases = _seed(tmp_path)
    al = identity.load_person_aliases(path=aliases)
    assert identity.person_for_name("Chau", al) == "p001"
    assert identity.person_for_name("LONG CHAU TRAN", al) == "p001"  # case-insensitive
    assert identity.person_for_name("eyyy", al) == "p001"  # same person, third nickname
    assert identity.person_for_name("Dao", al) == "p002"
    assert identity.person_for_name("nobody", al) is None


def test_aliases_for_person(tmp_path):
    _, aliases = _seed(tmp_path)
    al = identity.load_person_aliases(path=aliases)
    names = {a["alias"] for a in identity.aliases_for_person("p001", al)}
    assert names == {"Chau", "Long Chau Tran", "eyyy"}


def test_known_alias_names_lowercased(tmp_path):
    _, aliases = _seed(tmp_path)
    al = identity.load_person_aliases(path=aliases)
    assert identity.known_alias_names(al) == {"chau", "long chau tran", "eyyy", "dao"}


def test_load_missing_returns_empty(tmp_path):
    assert identity.load_people(path=tmp_path / "nope.csv") == []
    assert identity.load_person_aliases(path=tmp_path / "nope.csv") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_identity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'badminton_tracker.identity'`

- [ ] **Step 3: Write identity.py**

Create `src/badminton_tracker/identity.py`:

```python
"""Person-centric identity model (PRIVATE files in data/ — never published).

A *person* (people.csv) owns many *aliases* (person_aliases.csv): nicknames,
real names, and any profile GUIDs they registered under across tournaments.
This lets one friend be tracked whether they appear as "Chau", "Long Chau Tran",
or "eyyy", and lets GUID-less friends (e.g. Dao) exist as first-class persons.

Matching is EXACT and case-insensitive — no fuzzy/token auto-linking (that
produced the wrong "Dao = Quinn Dao" mapping). All lookups operate on already-
loaded rows so they stay pure and unit-testable.
"""

from __future__ import annotations

import csv

from .config import PEOPLE_CSV, PERSON_ALIASES_CSV

PEOPLE_FIELDS = ["person_id", "real_name", "has_profile", "notes"]
ALIAS_FIELDS = ["person_id", "alias", "kind", "guid", "source_tournament", "confidence"]


def _load(path, fields) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return [{k: (r.get(k) or "").strip() for k in fields} for r in csv.DictReader(f)]


def _write(rows, path, fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def load_people(path=None) -> list[dict]:
    return _load(path or PEOPLE_CSV, PEOPLE_FIELDS)


def load_person_aliases(path=None) -> list[dict]:
    return _load(path or PERSON_ALIASES_CSV, ALIAS_FIELDS)


def write_people(rows, path=None) -> None:
    _write(rows, path or PEOPLE_CSV, PEOPLE_FIELDS)


def write_person_aliases(rows, path=None) -> None:
    _write(rows, path or PERSON_ALIASES_CSV, ALIAS_FIELDS)


def person_for_name(name: str, aliases=None) -> str | None:
    """Exact, case-insensitive alias → person_id. None if unknown."""
    if not name:
        return None
    aliases = load_person_aliases() if aliases is None else aliases
    target = name.strip().lower()
    for a in aliases:
        if a["alias"].lower() == target:
            return a["person_id"]
    return None


def aliases_for_person(person_id: str, aliases=None) -> list[dict]:
    aliases = load_person_aliases() if aliases is None else aliases
    return [a for a in aliases if a["person_id"] == person_id]


def known_alias_names(aliases=None) -> set[str]:
    aliases = load_person_aliases() if aliases is None else aliases
    return {a["alias"].lower() for a in aliases if a["alias"]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_identity.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check
git add src/badminton_tracker/identity.py tests/test_identity.py
git commit -m "Add identity.py: person-centric multi-nickname model + lookups"
```

---

### Task 3: identity-seed — migrate players.csv → people + person_aliases

**Files:**
- Create: `src/badminton_tracker/identity_seed.py`
- Modify: `src/badminton_tracker/__main__.py` (add `identity-seed` verb)
- Test: `tests/test_identity_seed.py`

**Interfaces:**
- Consumes: `identity.PEOPLE_FIELDS/ALIAS_FIELDS`, `identity.write_people/write_person_aliases`.
- Produces:
  - `build_seed(player_rows) -> tuple[list[dict], list[dict]]` — pure: returns `(people_rows, alias_rows)` from a list of players.csv-shaped dicts.
  - `seed_identity(players_csv=None, people_csv=None, aliases_csv=None) -> tuple[int, int]` — reads players.csv, writes the two files, returns `(n_people, n_aliases)`.

**Seed rules (deterministic):**
- One person per players.csv row. `person_id` = `p001`, `p002`, … in file order (zero-padded to 3).
- `real_name` = the row's `full_name` if present, else its `nickname`.
- `has_profile` = `"y"` if the row has a non-empty `profile_guid`, else `"n"`.
- Alias rows for each person: the `nickname` (kind=`nickname`) and, when `full_name` differs from `nickname` and is non-empty, the `full_name` (kind=`realname`, carrying the `profile_guid` if any). `confidence` copied from the players.csv row (default `"low"`).
- Dedupe alias text within a person (case-insensitive) so a row where nickname==full_name yields one alias.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_identity_seed.py`:

```python
# tests/test_identity_seed.py
from __future__ import annotations

from badminton_tracker import identity_seed


PLAYER_ROWS = [
    {"nickname": "Chau", "full_name": "Long Chau Tran",
     "profile_guid": "d69f71b9-69f2-472e-97b2-4fc80ac43a17", "confidence": "low"},
    {"nickname": "Dao", "full_name": "Chompoonooch Unwong",
     "profile_guid": "", "confidence": "high"},
    {"nickname": "Hien Köhler", "full_name": "Hien Köhler",
     "profile_guid": "215c485f-ed48-4a86-8148-512d35849392", "confidence": "high"},
]


def test_build_seed_one_person_per_row_with_ids():
    people, _ = identity_seed.build_seed(PLAYER_ROWS)
    assert [p["person_id"] for p in people] == ["p001", "p002", "p003"]
    assert people[0]["real_name"] == "Long Chau Tran"


def test_build_seed_guid_presence_sets_has_profile():
    people, _ = identity_seed.build_seed(PLAYER_ROWS)
    assert people[0]["has_profile"] == "y"   # has GUID
    assert people[1]["has_profile"] == "n"   # Dao, GUID-less, first-class
    assert people[2]["has_profile"] == "y"


def test_build_seed_aliases_nickname_and_realname():
    _, aliases = identity_seed.build_seed(PLAYER_ROWS)
    p001 = [a for a in aliases if a["person_id"] == "p001"]
    by_text = {a["alias"]: a for a in p001}
    assert set(by_text) == {"Chau", "Long Chau Tran"}
    assert by_text["Chau"]["kind"] == "nickname"
    assert by_text["Long Chau Tran"]["kind"] == "realname"
    # The GUID rides on the realname alias only.
    assert by_text["Long Chau Tran"]["guid"] == "d69f71b9-69f2-472e-97b2-4fc80ac43a17"
    assert by_text["Chau"]["guid"] == ""


def test_build_seed_dedupes_when_nickname_equals_fullname():
    _, aliases = identity_seed.build_seed(PLAYER_ROWS)
    p003 = [a for a in aliases if a["person_id"] == "p003"]
    # "Hien Köhler" nickname == full_name -> exactly one alias row.
    assert len(p003) == 1
    assert p003[0]["alias"] == "Hien Köhler"


def test_seed_identity_writes_both_files(tmp_path):
    import csv
    players = tmp_path / "players.csv"
    with open(players, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["nickname", "full_name", "profile_guid",
                                          "profile_url", "confidence", "include"])
        w.writeheader()
        for r in PLAYER_ROWS:
            w.writerow({**r, "profile_url": "", "include": ""})
    people_csv = tmp_path / "people.csv"
    aliases_csv = tmp_path / "person_aliases.csv"
    n_people, n_aliases = identity_seed.seed_identity(
        players_csv=players, people_csv=people_csv, aliases_csv=aliases_csv)
    assert n_people == 3
    assert n_aliases == 4  # Chau(2) + Dao(1) + Hien(1)
    assert people_csv.exists() and aliases_csv.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_identity_seed.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'badminton_tracker.identity_seed'`

- [ ] **Step 3: Write identity_seed.py**

Create `src/badminton_tracker/identity_seed.py`:

```python
"""One-time migration: players.csv -> people.csv + person_aliases.csv.

Each existing players.csv row becomes one person (p001, p002, …). The row's
nickname and (when different) full_name become alias rows; the profile_guid
rides on the realname alias. GUID-less friends get has_profile="n" — they are
first-class persons, tracked by name. Review the output before committing it to
the private data/ repo (rule #7).
"""

from __future__ import annotations

import csv

from .config import PEOPLE_CSV, PERSON_ALIASES_CSV, PLAYERS_CSV
from . import identity


def _pid(i: int) -> str:
    return f"p{i:03d}"


def build_seed(player_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    people: list[dict] = []
    aliases: list[dict] = []
    for i, row in enumerate(player_rows, start=1):
        pid = _pid(i)
        nickname = (row.get("nickname") or "").strip()
        full_name = (row.get("full_name") or "").strip()
        guid = (row.get("profile_guid") or "").strip()
        confidence = (row.get("confidence") or "low").strip() or "low"
        real_name = full_name or nickname
        people.append({
            "person_id": pid,
            "real_name": real_name,
            "has_profile": "y" if guid else "n",
            "notes": "",
        })
        seen: set[str] = set()
        if nickname:
            seen.add(nickname.lower())
            aliases.append({"person_id": pid, "alias": nickname, "kind": "nickname",
                            "guid": "", "source_tournament": "", "confidence": confidence})
        if full_name and full_name.lower() not in seen:
            aliases.append({"person_id": pid, "alias": full_name, "kind": "realname",
                            "guid": guid, "source_tournament": "", "confidence": confidence})
    return people, aliases


def _read_players(path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def seed_identity(players_csv=None, people_csv=None, aliases_csv=None) -> tuple[int, int]:
    player_rows = _read_players(players_csv or PLAYERS_CSV)
    people, aliases = build_seed(player_rows)
    identity.write_people(people, path=people_csv or PEOPLE_CSV)
    identity.write_person_aliases(aliases, path=aliases_csv or PERSON_ALIASES_CSV)
    return len(people), len(aliases)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_identity_seed.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Wire the `identity-seed` CLI verb**

In `src/badminton_tracker/__main__.py`, add a subparser after the `p_upc` block (before `args = parser.parse_args()`):

```python
    sub.add_parser("identity-seed", help="build people.csv + person_aliases.csv from players.csv")
```

And add a handler branch after the `upcoming` branch:

```python
    elif args.command == "identity-seed":
        from .identity_seed import seed_identity

        n_people, n_aliases = seed_identity()
        print(f"Seeded {n_people} people, {n_aliases} aliases. "
              "Review data/people.csv + data/person_aliases.csv, then commit to the data/ repo.")
```

- [ ] **Step 6: Verify the verb is wired (no scrape; just argparse)**

Run: `uv run badminton --help`
Expected: the help text lists `identity-seed`. (Do NOT run `identity-seed` for real yet — that writes real data files; the human does that during the goal-#1/seed step and reviews before committing.)

- [ ] **Step 7: Lint + commit**

```bash
uv run ruff check
git add src/badminton_tracker/identity_seed.py src/badminton_tracker/__main__.py tests/test_identity_seed.py
git commit -m "Add identity-seed: migrate players.csv to people + person_aliases"
```

---

### Task 4: discovery_queue.py — harvest split + queue I/O

**Files:**
- Create: `src/badminton_tracker/discovery_queue.py`
- Test: `tests/test_discovery_queue.py`

**Interfaces:**
- Consumes: `identity.known_alias_names`, `config.DISCOVERY_CANDIDATES_CSV`.
- Produces:
  - `QUEUE_FIELDS = ["seen_name", "kind", "where_seen", "alongside", "suggested_person_id", "confidence", "decision"]`
  - `load_queue(path=None) -> list[dict]`, `write_queue(rows, path=None) -> None`
  - `split_sightings(sightings, known_names, queued_names) -> tuple[list[dict], list[dict]]` — pure. `sightings` = list of dicts with keys `seen_name,kind,where_seen,alongside`. Returns `(known_hits, new_candidates)`: a sighting whose lowercased `seen_name` is in `known_names` → known_hit (silent, provenance only); otherwise → new candidate row (QUEUE_FIELDS shape, `suggested_person_id=""`, `confidence="new"`, `decision=""`). De-dupes new candidates against `queued_names` (already in the queue) AND within the same batch, both case-insensitively.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_discovery_queue.py`:

```python
# tests/test_discovery_queue.py
from __future__ import annotations

from badminton_tracker import discovery_queue as dq


def test_split_known_vs_new():
    sightings = [
        {"seen_name": "Santeri", "kind": "opponent", "where_seen": "Hien's profile", "alongside": "Hien"},
        {"seen_name": "Thy", "kind": "opponent", "where_seen": "Santeri's profile", "alongside": "Santeri"},
    ]
    known = {"santeri"}  # Santeri is already a known alias
    known_hits, new = dq.split_sightings(sightings, known, queued_names=set())
    assert [h["seen_name"] for h in known_hits] == ["Santeri"]
    assert [n["seen_name"] for n in new] == ["Thy"]
    assert new[0]["confidence"] == "new"
    assert new[0]["decision"] == ""
    assert new[0]["suggested_person_id"] == ""


def test_split_is_case_insensitive():
    sightings = [{"seen_name": "SANTERI", "kind": "partner", "where_seen": "x", "alongside": "y"}]
    known_hits, new = dq.split_sightings(sightings, {"santeri"}, queued_names=set())
    assert len(known_hits) == 1 and not new


def test_split_dedupes_against_queue_and_within_batch():
    sightings = [
        {"seen_name": "Thy", "kind": "opponent", "where_seen": "a", "alongside": "b"},
        {"seen_name": "thy", "kind": "partner", "where_seen": "c", "alongside": "d"},  # dup in batch
        {"seen_name": "Tong", "kind": "opponent", "where_seen": "e", "alongside": "f"},
    ]
    known_hits, new = dq.split_sightings(sightings, known_names=set(), queued_names={"tong"})
    # "thy" once (batch dedupe), "Tong" suppressed (already queued)
    assert [n["seen_name"] for n in new] == ["Thy"]


def test_queue_round_trip(tmp_path):
    path = tmp_path / "discovery_candidates.csv"
    rows = [{"seen_name": "Thy", "kind": "opponent", "where_seen": "Santeri's profile",
             "alongside": "Santeri", "suggested_person_id": "", "confidence": "new", "decision": ""}]
    dq.write_queue(rows, path=path)
    back = dq.load_queue(path=path)
    assert back == rows


def test_load_missing_queue_is_empty(tmp_path):
    assert dq.load_queue(path=tmp_path / "nope.csv") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_discovery_queue.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'badminton_tracker.discovery_queue'`

- [ ] **Step 3: Write discovery_queue.py**

Create `src/badminton_tracker/discovery_queue.py`:

```python
"""The name-based discovery review queue (data/discovery_candidates.csv).

Discovery harvests names seen next to confirmed friends (partners/opponents) and
on chosen tournament participant lists. A name already known as an alias is a
silent provenance hit; an unknown name becomes a candidate row the human reviews
and decides (fills `decision` with a person_id). NOTHING auto-links a name to a
person — this is the deliberate guard against the wrong-fuzzy-match class.
"""

from __future__ import annotations

import csv

from .config import DISCOVERY_CANDIDATES_CSV

QUEUE_FIELDS = ["seen_name", "kind", "where_seen", "alongside",
                "suggested_person_id", "confidence", "decision"]


def load_queue(path=None) -> list[dict]:
    path = path or DISCOVERY_CANDIDATES_CSV
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return [{k: (r.get(k) or "").strip() for k in QUEUE_FIELDS} for r in csv.DictReader(f)]


def write_queue(rows, path=None) -> None:
    path = path or DISCOVERY_CANDIDATES_CSV
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=QUEUE_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in QUEUE_FIELDS})


def split_sightings(sightings, known_names, queued_names):
    """Partition sightings into (known_hits, new_candidates).

    known_names / queued_names are sets of LOWERCASED names. A sighting whose
    seen_name is already a known alias is a silent provenance hit; otherwise it
    becomes a new candidate, de-duped against the existing queue and within the
    same batch (both case-insensitive).
    """
    known_hits = []
    new_candidates = []
    batch_seen: set[str] = set()
    for s in sightings:
        name = (s.get("seen_name") or "").strip()
        low = name.lower()
        if not name:
            continue
        if low in known_names:
            known_hits.append(s)
            continue
        if low in queued_names or low in batch_seen:
            continue
        batch_seen.add(low)
        new_candidates.append({
            "seen_name": name,
            "kind": s.get("kind", ""),
            "where_seen": s.get("where_seen", ""),
            "alongside": s.get("alongside", ""),
            "suggested_person_id": "",
            "confidence": "new",
            "decision": "",
        })
    return known_hits, new_candidates
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_discovery_queue.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check
git add src/badminton_tracker/discovery_queue.py tests/test_discovery_queue.py
git commit -m "Add discovery_queue: harvest split + review-queue I/O"
```

---

### Task 5: identity-confirm — fold decided candidates into person_aliases.csv

**Files:**
- Modify: `src/badminton_tracker/discovery_queue.py` (add `fold_decisions`)
- Modify: `src/badminton_tracker/__main__.py` (add `identity-confirm` verb)
- Test: `tests/test_discovery_queue.py` (add fold tests)

**Interfaces:**
- Consumes: `identity.ALIAS_FIELDS`, `QUEUE_FIELDS`.
- Produces:
  - `fold_decisions(queue_rows, existing_aliases) -> tuple[list[dict], list[dict]]` — pure. Returns `(new_alias_rows, remaining_queue_rows)`. A queue row with a non-empty `decision` (a person_id) becomes an alias row (`person_id`=decision, `alias`=seen_name, `kind`="nickname", `guid`="", `source_tournament`=where_seen, `confidence`="confirmed") and is removed from the queue. Rows with blank `decision` stay in the queue. Skip a decided row if that (person_id, alias-lowercased) already exists in `existing_aliases` (idempotent).

- [ ] **Step 1: Write the failing fold tests**

Append to `tests/test_discovery_queue.py`:

```python
def test_fold_decisions_creates_alias_and_clears_row():
    queue = [
        {"seen_name": "eyyy", "kind": "participant", "where_seen": "Kaarina May 2026",
         "alongside": "", "suggested_person_id": "p001", "confidence": "fuzzy", "decision": "p001"},
        {"seen_name": "Mystery", "kind": "opponent", "where_seen": "x",
         "alongside": "y", "suggested_person_id": "", "confidence": "new", "decision": ""},
    ]
    new_aliases, remaining = dq.fold_decisions(queue, existing_aliases=[])
    assert len(new_aliases) == 1
    a = new_aliases[0]
    assert a["person_id"] == "p001" and a["alias"] == "eyyy"
    assert a["kind"] == "nickname" and a["confidence"] == "confirmed"
    assert a["source_tournament"] == "Kaarina May 2026"
    # Undecided row stays queued; decided row removed.
    assert [r["seen_name"] for r in remaining] == ["Mystery"]


def test_fold_is_idempotent_against_existing_aliases():
    queue = [{"seen_name": "Eyyy", "kind": "participant", "where_seen": "K",
              "alongside": "", "suggested_person_id": "p001",
              "confidence": "fuzzy", "decision": "p001"}]
    existing = [{"person_id": "p001", "alias": "eyyy", "kind": "nickname",
                 "guid": "", "source_tournament": "", "confidence": "confirmed"}]
    new_aliases, remaining = dq.fold_decisions(queue, existing_aliases=existing)
    assert new_aliases == []          # already linked, no duplicate
    assert remaining == []            # still consumed from the queue
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_discovery_queue.py -v`
Expected: FAIL — `AttributeError: module 'badminton_tracker.discovery_queue' has no attribute 'fold_decisions'`

- [ ] **Step 3: Add fold_decisions to discovery_queue.py**

Add `from .identity import ALIAS_FIELDS` near the top imports, then append:

```python
def fold_decisions(queue_rows, existing_aliases):
    """Turn decided queue rows into alias rows; return (new_aliases, remaining_queue).

    A row whose `decision` holds a person_id is consumed: it becomes a confirmed
    nickname alias (unless that (person_id, alias) already exists — idempotent).
    Undecided rows (blank `decision`) stay in the queue.
    """
    have = {(a["person_id"], a["alias"].lower()) for a in existing_aliases}
    new_aliases = []
    remaining = []
    for r in queue_rows:
        decision = (r.get("decision") or "").strip()
        if not decision:
            remaining.append(r)
            continue
        key = (decision, (r.get("seen_name") or "").strip().lower())
        if key in have:
            continue  # already linked; consume without duplicating
        have.add(key)
        new_aliases.append({
            "person_id": decision,
            "alias": (r.get("seen_name") or "").strip(),
            "kind": "nickname",
            "guid": "",
            "source_tournament": (r.get("where_seen") or "").strip(),
            "confidence": "confirmed",
        })
    return new_aliases, remaining
```

(`ALIAS_FIELDS` is imported to document the alias-row shape and keep the modules' contract aligned; the dict literal above matches it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_discovery_queue.py -v`
Expected: PASS (7 tests total)

- [ ] **Step 5: Wire the `identity-confirm` CLI verb**

In `__main__.py`, add the subparser:

```python
    sub.add_parser("identity-confirm",
                   help="fold decided discovery_candidates.csv rows into person_aliases.csv")
```

And the handler branch:

```python
    elif args.command == "identity-confirm":
        from . import identity
        from .discovery_queue import fold_decisions, load_queue, write_queue

        queue = load_queue()
        existing = identity.load_person_aliases()
        new_aliases, remaining = fold_decisions(queue, existing)
        if new_aliases:
            identity.write_person_aliases(existing + new_aliases)
        write_queue(remaining)
        print(f"Confirmed {len(new_aliases)} new alias(es); {len(remaining)} row(s) still pending. "
              "Commit data/person_aliases.csv + data/discovery_candidates.csv to the data/ repo.")
```

- [ ] **Step 6: Verify the verb is wired**

Run: `uv run badminton --help`
Expected: help lists `identity-confirm`.

- [ ] **Step 7: Lint + commit**

```bash
uv run ruff check
git add src/badminton_tracker/discovery_queue.py src/badminton_tracker/__main__.py tests/test_discovery_queue.py
git commit -m "Add identity-confirm: fold decided candidates into person_aliases"
```

---

### Task 6: discover_names.py — live Playwright drivers (Source A + Source B)

**Files:**
- Create: `src/badminton_tracker/discover_names.py`
- Modify: `src/badminton_tracker/__main__.py` (add `discover-names` verb with `--tournament`, `--go`, `--max-pages`)

**Interfaces:**
- Consumes: `client.new_context/ensure_login/dismiss_cookies`, `fetch.load_players`, `discover._load_profile`/`_names_in_match`, `identity.known_alias_names`/`load_person_aliases`, `discovery_queue.split_sightings`/`load_queue`/`write_queue`, `config.BASE_URL`.
- Produces:
  - `harvest_from_friends() -> list[dict]` — sightings (`seen_name,kind,where_seen,alongside`) from confirmed friends' match pages. `# pragma: no cover`.
  - `scan_participants(tournament_guids, go, max_pages) -> list[dict]` — sightings from participant lists; when `go=False`, prints the dry-run plan and returns `[]`. `# pragma: no cover`.
  - `run_discover_names(tournament_guids=None, go=False, max_pages=20) -> int` — orchestrates: gather sightings → `split_sightings` against known aliases + existing queue → append new candidates → `write_queue`. Returns count of new candidates. `# pragma: no cover`.

This task is the network-heavy driver; its parsing inputs (already covered by Task 4's pure `split_sightings`) are unit-tested, so the driver itself is `# pragma: no cover` and verified manually against the live site (rule #6).

- [ ] **Step 1: Write discover_names.py**

Create `src/badminton_tracker/discover_names.py`:

```python
"""Name-based discovery drivers (live; manually verified — see rule #6).

Source A (cheap, runs freely): walk confirmed friends' player-profile match pages
and harvest the partner/opponent names beside them.
Source B (ban-risky, gated): for explicitly-named tournaments, scan the
participant list. Defaults to a DRY RUN that only prints what it would fetch;
pass go=True (CLI --go) to actually scrape, throttled and page-capped.

All harvested names go through discovery_queue.split_sightings, so nothing is
auto-linked to a person. Drivers are # pragma: no cover; the matching logic they
feed is unit-tested in test_discovery_queue.py.
"""

from __future__ import annotations

from . import identity
from .config import BASE_URL
from .discovery_queue import load_queue, split_sightings, write_queue


def harvest_from_friends() -> list[dict]:  # pragma: no cover - live driver
    from playwright.sync_api import sync_playwright

    from .client import ensure_login, new_context
    from .discover import _load_profile, _names_in_match
    from .fetch import load_players

    players = load_players()
    sightings: list[dict] = []
    with sync_playwright() as p:
        browser, ctx = new_context(p)
        page = ensure_login(ctx)
        for pl in players:
            owner = pl["nickname"] or pl["full_name"]
            print(f"[friends] harvesting {owner} ({pl['guid'][:8]}…)")
            for m in _load_profile(page, pl["guid"]):
                for name, role in _names_in_match(m):
                    sightings.append({"seen_name": name, "kind": role,
                                      "where_seen": f"{owner}'s profile", "alongside": owner})
            page.wait_for_timeout(800)  # politeness
        browser.close()
    return sightings


def scan_participants(tournament_guids, go, max_pages) -> list[dict]:  # pragma: no cover
    guids = list(tournament_guids or [])
    if not go:
        print("DRY RUN — would fetch participant lists for:")
        for g in guids:
            print(f"  {BASE_URL}/tournament/{g}/participants")
        print(f"(max_pages={max_pages}) Re-run with --go to actually scrape.")
        return []

    from playwright.sync_api import sync_playwright

    from .client import dismiss_cookies, ensure_login, new_context

    sightings: list[dict] = []
    with sync_playwright() as p:
        browser, ctx = new_context(p)
        page = ensure_login(ctx)
        pages_fetched = 0
        for g in guids:
            if pages_fetched >= max_pages:
                print(f"[participants] max_pages={max_pages} reached; stopping.")
                break
            url = f"{BASE_URL}/tournament/{g}/participants"
            print(f"[participants] fetching {url}")
            page.goto(url, wait_until="domcontentloaded")
            dismiss_cookies(page)
            page.wait_for_timeout(1200)  # throttle
            pages_fetched += 1
            for a in page.query_selector_all("a[href*=player]"):
                name = (a.inner_text() or "").strip()
                if name and len(name) > 2:
                    sightings.append({"seen_name": name, "kind": "participant",
                                      "where_seen": f"tournament {g}", "alongside": ""})
        browser.close()
    return sightings


def run_discover_names(tournament_guids=None, go=False, max_pages=20) -> int:  # pragma: no cover
    sightings = harvest_from_friends()
    sightings += scan_participants(tournament_guids, go, max_pages)

    aliases = identity.load_person_aliases()
    known = identity.known_alias_names(aliases)
    existing_queue = load_queue()
    queued = {r["seen_name"].lower() for r in existing_queue}

    known_hits, new_candidates = split_sightings(sightings, known, queued)
    write_queue(existing_queue + new_candidates)
    print(f"{len(known_hits)} known sighting(s) (silent); "
          f"{len(new_candidates)} new candidate(s) -> data/discovery_candidates.csv. "
          "Review, fill `decision`, then run: badminton identity-confirm.")
    return len(new_candidates)
```

- [ ] **Step 2: Verify it imports (no scrape)**

Run: `uv run python -c "from badminton_tracker.discover_names import run_discover_names; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Wire the `discover-names` CLI verb**

In `__main__.py`, add the subparser:

```python
    p_dn = sub.add_parser("discover-names",
                          help="harvest friend names into discovery_candidates.csv (review queue)")
    p_dn.add_argument("--tournament", action="append", default=[], metavar="GUID",
                      help="also scan this tournament's participant list (repeatable)")
    p_dn.add_argument("--go", action="store_true",
                      help="actually scrape participant lists (default is a dry run)")
    p_dn.add_argument("--max-pages", type=int, default=20,
                      help="cap on participant-list pages fetched (ban-risk guard)")
```

And the handler branch:

```python
    elif args.command == "discover-names":
        from .discover_names import run_discover_names

        run_discover_names(tournament_guids=args.tournament, go=args.go, max_pages=args.max_pages)
```

- [ ] **Step 4: Verify the verb + dry-run flag parse**

Run: `uv run badminton discover-names --help`
Expected: help shows `--tournament`, `--go`, `--max-pages`.

- [ ] **Step 5: Lint + commit (code only — no live scrape in this step)**

```bash
uv run ruff check
git add src/badminton_tracker/discover_names.py src/badminton_tracker/__main__.py
git commit -m "Add discover-names: friend-harvest + gated participant-list scan"
```

- [ ] **Step 6: MANUAL live verification (human-run; not part of automated tests)**

This is the live, ban-risky step — run by the human, not a subagent, with the env-shadow fix:

```bash
# Source A only (cheap):
unset TOURNAMENTSOFTWARE_USERNAME TOURNAMENTSOFTWARE_PASSWORD TOURNAMENTSOFTWARE_BASE_URL && uv run badminton discover-names
# Source B dry-run (prints plan, fetches nothing):
unset TOURNAMENTSOFTWARE_USERNAME TOURNAMENTSOFTWARE_PASSWORD TOURNAMENTSOFTWARE_BASE_URL && uv run badminton discover-names --tournament <KAARINA_GUID>
```
Expected: `data/discovery_candidates.csv` gains rows for GUID-less friends seen beside confirmed friends (e.g. Thy beside Santeri); the dry-run prints the participant-list URL and fetches nothing. Eyeball the file before committing it to the `data/` repo.

---

### Task 7: Privacy guard test — no GUID/person_id in public JSON

**Files:**
- Create: `tests/test_privacy_guards.py`

**Interfaces:**
- Consumes: `config.UPCOMING_JSON`; the historical public artifact `web/data.json` (path `config.ROOT / "web" / "data.json"`).

This is the rule-#4 enforcement net: it runs in the normal suite, so any future change that leaks a GUID or person_id into a public file fails CI.

- [ ] **Step 1: Write the guard test**

Create `tests/test_privacy_guards.py`:

```python
# tests/test_privacy_guards.py
"""Rule #4 enforcement: no GUIDs / person_ids may reach public web/*.json."""
from __future__ import annotations

import re

import pytest

from badminton_tracker.config import ROOT, UPCOMING_JSON

GUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
PERSON_ID_RE = re.compile(r'"person_id"')
PUBLIC_FILES = [ROOT / "web" / "data.json", UPCOMING_JSON]


@pytest.mark.parametrize("path", PUBLIC_FILES, ids=lambda p: p.name)
def test_public_json_has_no_guid(path):
    if not path.exists():
        pytest.skip(f"{path.name} not generated in this environment")
    text = path.read_text(encoding="utf-8")
    leaked = GUID_RE.findall(text)
    assert not leaked, f"{path.name} leaks profile GUID(s): {leaked[:3]}"


@pytest.mark.parametrize("path", PUBLIC_FILES, ids=lambda p: p.name)
def test_public_json_has_no_person_id(path):
    if not path.exists():
        pytest.skip(f"{path.name} not generated in this environment")
    text = path.read_text(encoding="utf-8")
    assert not PERSON_ID_RE.search(text), f"{path.name} leaks a person_id field"
```

- [ ] **Step 2: Run the guard test**

Run: `uv run pytest tests/test_privacy_guards.py -v`
Expected: PASS (or SKIP if the web/*.json files aren't present in the dev checkout — both are acceptable; a present file with a GUID FAILS).

- [ ] **Step 3: Run the FULL suite and lint (verify nothing regressed)**

Run: `uv run pytest -v && uv run ruff check`
Expected: all tests PASS, ruff clean. **Read the actual output — do not trust a summary (a prior subagent falsely reported passing tests).**

- [ ] **Step 4: Commit**

```bash
git add tests/test_privacy_guards.py
git commit -m "Add privacy-guard test: no GUID/person_id in public web/*.json"
```

---

## Post-implementation (human-run, outside the automated task loop)

These touch the private `data/` repo and the live site — done by the human, committed to `data/` via `versioning.commit` or `git -C data` (rule #7), reviewing each file first:

1. **Goal #1 — confirm Chau + easy GUID friends:** set `include=y` on the Chau row in `data/players.csv` (and, after eyeballing, the Tier-1 low-confidence GUID rows: Santeri, Junya, Maila, Toni, Tanisha, Dhirav, Matti). Commit to `data/`. Run `unset TOURNAMENTSOFTWARE_* && uv run badminton upcoming` and confirm Chau's upcoming tournaments appear.
2. **Seed identity:** `uv run badminton identity-seed`; review `data/people.csv` + `data/person_aliases.csv`; add Dao/Bonnie/Vu Luu as GUID-less persons if not already; add Chau's `eyyy` alias (source `Kaarina May 2026`). Commit to `data/`.
3. **Run discovery (Task 6 Step 6):** harvest friends + dry-run a tournament; review the queue; fill `decision`; `uv run badminton identity-confirm`; commit `data/`.

---

## Self-Review

**Spec coverage:**
- §1 confirm user/easy friends → Post-implementation step 1 (mechanical, human-run, as the spec framed it). ✓
- §2 people.csv + person_aliases.csv + identity.py + seed → Tasks 1, 2, 3. ✓
- §3 discovery review queue + Source A + Source B (dry-run) → Tasks 4, 6; queue I/O Task 4; fold Task 5. ✓
- §4 four verbs (identity-seed, discover-names, identity-confirm) + gitignore + privacy test + commits → Tasks 1, 3, 5, 6, 7; commit guidance in Post-implementation. ✓
- §5 testing: pure units (Tasks 2–5), live drivers `# pragma: no cover` (Task 6), privacy guard (Task 7), ruff clean each task, verify-subagent-claims called out in Task 7 Step 3. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code; live-driver `<KAARINA_GUID>` is an intentional human-supplied value, not a code placeholder. ✓

**Type consistency:** `QUEUE_FIELDS`, `PEOPLE_FIELDS`, `ALIAS_FIELDS` used consistently; `split_sightings`/`fold_decisions`/`load_queue`/`write_queue` signatures match across Tasks 4, 5, 6; alias-row dict shape in `fold_decisions` matches `ALIAS_FIELDS` and `identity.write_person_aliases`. ✓

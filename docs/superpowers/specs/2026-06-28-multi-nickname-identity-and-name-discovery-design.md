# Design — Multi-nickname identity + name-based discovery

**Date:** 2026-06-28
**Status:** APPROVED (brainstorming complete) — ready for implementation plan
**Repos touched:** public `Ihsara/badminton` (code), private `data/` (new identity files)

## Problem

The tracker can only follow people who have a tournamentsoftware **profile GUID**
that gets confirmed in `data/players.csv` (`include=Y` + `profile_guid`). Two gaps:

1. **GUID-less friends** (e.g. Dao = Chompoonooch Unwong, who had no license last
   year) have no profile, so the GUID-snowball discovery can never find them.
2. **One person, many nicknames across tournaments** — the user is "Chau" /
   "Long Chau Tran" in the roster but registered as **"eyyy"** at the May 2026
   Kaarina tournament. Today each name is an unrelated row; there is no concept
   of a *person*.

There is also a backlog: several friends (Santeri, Junya, Maila, Toni, Tanisha,
Dhirav, Matti) already resolved to a GUID during snowball discovery but were left
at `confidence=low` with blank `include`, so they are simply unconfirmed — "easy
to find back" without any new scraping.

## Goals

1. **Confirm the user (Chau) and other easy GUID-holders** for tracking
   (mechanical: flip `include=y`, commit to private repo, re-run the upcoming scrape).
2. **A multi-nickname identity model**: one person → many display nicknames /
   GUIDs across tournaments. The user is findable as "Chau", "Long Chau Tran", or
   "eyyy".
3. **Name-based discovery** that scans tournament participant/result lists and
   confirmed friends' match pages to find friends by ANY nickname (not by GUID),
   so GUID-less friends like Dao are tracked.
4. **Privacy preserved** (rule #4): no GUIDs / person_ids in public artifacts;
   the two-repo split (public code / private `data/`) is respected.

## Non-goals (YAGNI)

- Exposing person grouping on the public website (`web/data.json` stays as-is;
  no `person_id` in public output this iteration).
- Replacing `players.csv` / `load_players()` — the existing GUID-scrape path is
  left working and untouched.
- Time-window auto-enumeration of tournaments (explicit tournament list only).
- Fuzzy auto-linking of harvested names (this is what produced the wrong
  "Dao = Quinn Dao" mapping — deliberately excluded).

---

## Existing data-file map (ground truth)

### Private — live only in the nested `data/` repo, never published
| File | Schema | Purpose |
|---|---|---|
| `Badminton Bro Tournament Log v2.xlsx` | Date, Tournament, Player 1/2, Opponent 1/2, Result, sets | Source of truth for matches. `friend_names()` reads Player 1/2. |
| `players.csv` | nickname, full_name, profile_guid, profile_url, confidence, include | Identity linkage. `load_players()` gates on `include=Y` + GUID. **Has GUIDs.** |
| `players_candidates.csv` | …, appearances, roles, include | Raw snowball-discovery output. **Has GUIDs.** |
| `aliases.csv` | name, display, notes | name→display relabel; `display` reaches public site. No GUIDs. |
| `matches_mirror.csv` | match rows | CSV mirror of the Excel log. |
| `upcoming_state.json` | tournaments + GUIDs | Private re-fetch state for upcoming. **Has GUIDs.** |

### Public — the ONLY publishable artifacts (GUID-free, rule #4)
| File | Built by |
|---|---|
| `web/data.json` | `export.py` |
| `web/upcoming.json` | `upcoming_build.py` (`_strip_guids`) |

### Code that consumes identity
- `fetch.py::load_players()` → `players.csv` (include+GUID gate)
- `excel_source.py::friend_names()` → the Excel
- `aliases.py::alias_map()` → `aliases.csv` (public display)
- `discover.py` → writes `players_candidates.csv`; `roster.py::build_players_csv()` → writes `players.csv`

---

## Section 1 — Confirm the user (and easy GUID-holders) first

Mechanical, independent of the new model:

1. Set `include=y` on the **Chau / Long Chau Tran** row in `data/players.csv`.
2. Present the other Tier-1 rows that already have a GUID but blank `include`
   (Santeri, Junya, Maila, Toni, Tanisha, Dhirav, Matti); the user eyeballs and
   picks which to confirm. **No auto-confirm of `confidence=low` rows.**
3. Commit to the **private `data/` repo** (rule #7).
4. Run, with the env-shadow fix:
   `unset TOURNAMENTSOFTWARE_USERNAME TOURNAMENTSOFTWARE_PASSWORD TOURNAMENTSOFTWARE_BASE_URL && uv run badminton upcoming`
   and verify the user's upcoming tournaments now appear (evidence before claims, rule #6).

### Friend tiers (clarifies why confirming the easy ones powers finding the hard ones)
| Tier | Who | How tracked |
|---|---|---|
| 1. Has GUID, unconfirmed | Chau, Santeri, Junya, Maila, Toni, Tanisha, Dhirav, Matti | flip `include=Y` |
| 2. Has GUID, confirmed | Hien | already works |
| 3. No GUID | Dao, Bonnie, Vu Luu, Tong, Tum, Yudai, Thy, Bom, Boris, Khai… | name-based discovery (new) |

Confirming Tier-1/2 friends directly powers Tier-3 discovery: a GUID-less friend
(Thy) shows up as a partner/opponent **name** on a confirmed friend's (Santeri's)
match pages.

---

## Section 2 — Identity data model

Two new **private** files in `data/` (gitignored in the public repo).

### `data/people.csv` — one row per PERSON
```
person_id, real_name,           has_profile, notes
p001,      Long Chau Tran,      y,           me
p002,      Chompoonooch Unwong, n,           Dao — no license last year, no GUID
p003,      Hien Köhler,         y,
```
- `person_id` is opaque (`p001`…), **not a GUID** — safe to reference anywhere.
- `has_profile` = does this person have any GUID at all. GUID-less people (Dao)
  are first-class with `has_profile=n`.

### `data/person_aliases.csv` — many rows: every name/GUID a person is known by
```
person_id, alias,               kind,     guid,        source_tournament,     confidence
p001,      Chau,                nickname, ,            ,                      high
p001,      Long Chau Tran,      realname, d69f71b9-…,  ,                      high
p001,      eyyy,                nickname, ,            Kaarina May 2026,      confirmed
p002,      Dao,                 nickname, ,            ,                      high
p002,      Chompoonooch Unwong, realname, ,            Stadin kesäkisat 2025, high
```
- `kind` ∈ {nickname, realname}. `guid` may be empty (GUID-less alias).
- `source_tournament` = provenance: where this nickname was observed.
- **This file is private**; the public site never sees `person_id` or `guid`.

### New module `identity.py`
Pure loader + lookups over the two CSVs:
- `load_people() -> list[Person]`, `load_person_aliases() -> list[Alias]`
- `person_for_name(name) -> person_id | None` (exact, case-insensitive)
- `aliases_for_person(pid) -> list[Alias]`
- `names_to_resolve() -> list[(name, guid|None)]`
- write/round-trip helpers for both files.

### Seed migration (`badminton identity-seed`)
One-time: read current `players.csv` rows → create initial `people.csv` +
`person_aliases.csv` (one person per existing friend; nickname + full_name + GUID
become alias rows; GUID-less friends — Dao, Bonnie, Vu Luu — get `has_profile=n`
person rows). User reviews the seed output before it is committed.

### Relationship to existing files
- `players.csv` / `load_players()` **unchanged** — GUID-scrape path untouched.
- `aliases.csv` (public display) **unchanged** this iteration.

---

## Section 3 — Name-based discovery flow

Two sources, friends-first, both feeding ONE review file the user confirms by hand.
**Nothing auto-links a harvested name to a person** (avoids the Quinn-Dao class).

### `data/discovery_candidates.csv` — the proposal queue
```
seen_name, kind,        where_seen,         alongside, suggested_person_id, confidence, decision
Thy,       opponent,    Santeri's profile,  Santeri,   ,                    new,
eyyy,      participant, Kaarina May 2026,    ,          p001?,               fuzzy,
Tong,      partner,     Hien's profile,     Hien,      ,                    new,
```
- `decision` is the user's: fill in a `person_id` (existing or new). Blank = undecided.
- `suggested_person_id` may carry a hint (with `?`) but is never applied automatically.

### Source A — confirmed-friends harvest (cheap, ~10 pages, low ban-risk; runs freely)
- For each confirmed person with a GUID, load `/player-profile/{guid}/tournaments`
  (reuse `_load_profile` from `discover.py`), collect partner/opponent names.
- Per name:
  - **Exact match** to an existing alias → record provenance **silently** (no review noise).
  - **New/unknown** → append to `discovery_candidates.csv`, `decision` blank.
- Surfaces Thy via Santeri, Tong via Hien, etc.

### Source B — participant-list scan (ban-risky; gated)
- User passes explicit tournament GUIDs/URLs.
- **`--dry-run` is the default**: prints exactly which pages it would fetch, then stops.
- `--go` actually scrapes: throttled (per-page `wait_for_timeout`, `--max-pages` cap),
  reads the participant/entry list, matches each entry name against all known aliases,
  flags unknowns into the review file.
- Catches "eyyy" at Kaarina and friends who never played a tracked friend.

---

## Section 4 — CLI verbs + privacy guards

### New CLI verbs (in `__main__.py`, matching the existing verb pattern)
| Verb | Behaviour |
|---|---|
| `badminton identity-seed` | Build `people.csv` + `person_aliases.csv` from `players.csv`; print summary for review. |
| `badminton discover-names` | Source A harvest → append to `discovery_candidates.csv`. Cheap, runs freely. |
| `badminton discover-names --tournament <guid> [--go] [--max-pages N]` | Source B scan. `--dry-run` default; `--go` to scrape. |
| `badminton identity-confirm` | Fold `discovery_candidates.csv` rows with a filled `decision` into `person_aliases.csv`; clear handled rows. |

### Privacy guards (rule #4)
1. Add `data/people.csv`, `data/person_aliases.csv`, `data/discovery_candidates.csv`
   to the **public `.gitignore`** (they live only in the private `data/` repo).
2. **`tests/test_privacy_guards.py`**: assert no `person_id`, no `guid`, and no
   profile-GUID pattern appears in `web/data.json` or `web/upcoming.json`. Runs in
   the normal suite, so a leak fails CI.
3. Pre-push checklist (`git ls-files | grep -E 'data/|\.env'` empty) per rule #4.

### Commits (rule #7)
`identity-seed`, `identity-confirm`, and any alias edit are committed to the
private `data/` repo with a message (reuse `versioning.py` if it fits, else
`git -C data commit`).

---

## Section 5 — Testing strategy

Pattern: pure functions unit-tested; Playwright drivers `# pragma: no cover`,
verified manually against the live site.

### Pure, unit-tested
- `identity.py` lookups + CSV round-trip. Fixtures include a GUID-less person
  (Dao) and a multi-nickname person (Chau/eyyy).
- Seed migration: sample `players.csv` → expected `people.csv` + `person_aliases.csv`.
- Candidate harvesting: parsed match dicts + known-alias set → correct
  new-vs-known split (exact-known silent, unknown → queue). Pure over parsed data.
- `identity-confirm` fold: candidates with filled `decision` → correct
  `person_aliases.csv` additions + cleared rows.
- `test_privacy_guards.py`: no GUID/person_id in `web/*.json`.

### Manual / live-verified (thin drivers, `# pragma: no cover`)
- Source A page-load + Source B participant-list fetch — run against live site
  (login via cookie-wall fix), eyeball the candidate file. Evidence before claims (rule #6).

### Hygiene
- Saved HTML fixtures GUID-scrubbed before landing in public `tests/`.
- `uv run ruff check` clean before any "done" claim (rule #2).
- **Verify subagent test claims directly** — re-run `uv run pytest` and read
  output; a prior subagent falsely reported passing tests.

---

## Open risks
- IP-ban risk on Source B → mitigated by explicit tournament list + dry-run default + throttle + max-pages.
- False identity links → mitigated by review-file gating (no auto-link).
- GUID leak → mitigated by gitignore + automated privacy-guard test + pre-push checklist.

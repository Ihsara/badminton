# Design: Tournament-first auto-discovery for the upcoming timeline

**Date:** 2026-06-28
**Status:** APPROVED (design); plan pending
**Supersedes / extends:** `2026-06-28-upcoming-tournament-timeline-design.md`
(the original friend-profile-driven pipeline shipped as PR #1).

## Problem

The shipped `badminton upcoming` pipeline (`upcoming_build.run_upcoming`) discovers
upcoming entries by walking each **confirmed friend's GLOBAL player-profile**
(`/player-profile/{GUID}/tournaments`) and reading the upcoming-entry cards.

This misses real entries in two structural ways:

1. **GUID-only discovery.** `fetch.load_players()` returns only friends with a
   `profile_guid` AND `include=Y`. Today that is essentially just Hien. GUID-less
   friends (Maila, Thy Nguyen, Dao, …) are never discovered at all.
2. **Scoped entries don't surface on global profiles.** Even for a GUID-friend,
   a tournament entry frequently appears ONLY on the **tournament-scoped** player
   page (`/tournament/{GUID}/player/{N}`), not the global profile — the same
   nickname/scoping issue documented for "Chau = Eyyy at Kesäyön".

Observed 2026-06-28: for **Stadin Sulan kesäkisat 4.7.2026** the pipeline wrote
`{"tournaments": []}` even though 7 friends were entered with a fully published
order-of-play (rounds, court "Talihalli", exact times). The schedule had to be
scraped by hand from the scoped player pages and assembled manually.

Codex review of PR #1 also flagged four real defects in the draw-based path
(see "Folded-in fixes" below); the P1 nickname-matching bug is the same class of
failure as the empty result.

## Goals

- Make `badminton upcoming` **find upcoming tournaments itself** and build the
  per-friend timeline automatically, without the user naming tournaments.
- Discover **all** confirmed friends in a tournament, including GUID-less ones,
  by **full-name** matching against the tournament's participant list.
- Use the **scoped player page's order-of-play** as the primary schedule source
  (real times/courts); use the draw bracket only to project rounds not yet
  scheduled.
- Stay **privacy-safe** (public `web/upcoming.json` is GUID-free; GUIDs live only
  in the gitignored `data/upcoming_state.json`).
- Be a **good citizen** against the live site (bounded, throttled, cached).

## Non-goals (YAGNI)

- No historical-results ingest — that remains the Excel flow, run *after* a
  tournament is played (`context/prompts/ingest-new-tournament.md`).
- No new web UI — the existing `#/upcoming` view in `web/app.js` already renders
  the `tournaments[].entries[].path[]` shape this produces.
- No identity-model (people.csv / person_aliases.csv) work — orthogonal, planned
  separately.
- No change to the historical `badminton build`/`export` paths.

## Architecture & data flow

Tournament-first; the old friend-profile walk becomes a fallback.

```
find upcoming tournaments            upcoming_find.py        (NEW)
  via /find/tournament window
  └─ for each tournament (bounded, throttled, cache-aware):
       fetch /tournament/{G}/players
       match friend group by FULL    upcoming_participants.py (NEW, pure)
         name → [{nick, full_name, player_no}]
       └─ for each matched friend:
            fetch /tournament/{G}/player/{N}
            parse .match cards →      upcoming_schedule_parse.py (NEW, pure)
              schedule nodes (round, event, partner, opponents, court, ISO time)
            if knockout & rounds unscheduled:
              resolve (tournament,event) draw → parse_draw → build_path
              project ONLY the rounds with no scheduled match
       assemble entry: scheduled nodes first, projected nodes appended
  assemble_upcoming(...)              upcoming_build.py       (REUSE)
    strip GUIDs, apply aliases, stamp generated_at
  write web/upcoming.json (public)  +  data/upcoming_state.json (private cache)
```

**Fallback:** any confirmed GUID-friend NOT found in a scanned participant list
(e.g. their tournament fell outside the finder window) is still picked up by the
existing global-profile walk, so coverage never regresses.

## Components (each independently testable)

### `upcoming_find.py` (new)
- `find_upcoming_tournaments(html: str, today_iso: str, horizon_days: int) -> list[dict]`
  — **pure**. Parse the finder result DOM (`a[href*="/sport/tournament?id="]`,
  skipping `ILMOITTAUTUMINEN`/online-entry links) into
  `[{name, guid, start_date, end_date}]`, keeping only those within
  `[today, today + horizon_days]`.
- Thin driver: build the finder URL window, fetch (cookie-wall aware), feed HTML
  to the pure parser. `# pragma: no cover`.
- **Note on the finder:** the live finder ignores explicit date params and serves
  a default upcoming window with its own pagination; the driver must paginate
  defensively and de-dupe by GUID rather than trust the query string.

### `upcoming_participants.py` (new, pure)
- `match_friends(participants: list[dict], roster: list[dict], exclude: set[str])
   -> list[dict]` returning `[{nickname, full_name, player_no}]`.
- Participant = `{name, player_no}` parsed from `a[href*="player.aspx"]` on the
  `/players` page (the parse of the anchor list is a tiny pure helper here too).
- **Matching rule (the rule-heavy core — most tests live here):**
  - FULL-name only: every token of a roster full_name present in the participant
    name (order-independent; handles "Köhler, Hien" surname-first form).
  - Vietnamese registrations for Chau: accept `chau`+`tran` OR `chau`+`long`
    (so "Trần Long Châu"/"Châu Trần"/"Long Chau Tran" match), while excluding
    "Chau Vu"/"Quan Chau".
  - Apply the `exclude` set (Yuki Matti; the wrong Toni) — no match even on a
    full-name hit.
  - Never single-token match.

### `upcoming_schedule_parse.py` (new, pure)
- `parse_player_schedule(html: str, friend_full_name: str)
   -> list[dict]` → one node per `.match` card:
  `{round, event, partner, opponent, court, time (ISO|None), time_kind, state}`.
- Promotes the verified one-off extractor used to publish Stadin: collapse the
  duplicated `.match__row` names, strip seed markers `[1]`, identify the friend's
  own team to name the opponent, parse the Finnish `d.m.yyyy HH.MM` footer into
  an ISO datetime, read the court from the footer.
- `state` defaults to `"scheduled"` (these are published but unplayed); a result,
  if present, flips it to `"done"`.

### `upcoming_build.py` (modified driver)
- `run_upcoming()` re-orchestrated to the tournament-first flow above. Remains
  `# pragma: no cover` (live driver).
- Reuses `assemble_upcoming`, `_strip_guids`, `write_outputs` unchanged.
- Draw resolution cache keyed by **(tournament_guid, event)** (fixes Codex P2).
- Schedule nodes carry the **site full name**; the display nickname is applied
  only by `assemble_upcoming`'s alias pass (fixes Codex P1).

### `data/exclude.csv` (new private data file)
- Columns: `name,reason`. Seeds: `Yuki Matti,no license/never on TS`;
  `Toni Seppälä,wrong Toni identity`.
- Loaded into the `exclude` set; replaces hardcoded exclusion knowledge. Lives in
  the private `data/` repo (never published).

## CLI surface

- `badminton upcoming` — now auto-discovers (bounded window). Default behavior.
- `badminton upcoming --tournament GUID` (repeatable) — force-include specific
  tournaments in addition to auto-discovery (e.g. one outside the window).
- `badminton upcoming --watch` — unchanged (loops via `upcoming_schedule.watch`).
- `--horizon-days N` (default 60) and `--max-tournaments N` caps exposed as flags
  with safe defaults.

## Scan policy — bounded auto + politeness

- **Horizon:** default 60 days ahead.
- **Caps:** `--max-tournaments` per run; max participant-list pages per
  tournament; only fetch scoped pages for *matched* friends (not all 180+
  participants).
- **Throttle:** reuse the existing `page.wait_for_timeout(...)` politeness delays
  between fetches.
- **Cache:** `data/upcoming_state.json` keyed by tournament GUID. Each cached
  tournament stores a `fetched_at` timestamp. Re-fetch policy: skip a tournament
  if it was fetched within a TTL (default 6h) AND its start_date is still
  more than 24h away; always re-fetch within the final 24h before start (schedules
  change late). This is a simple time-based policy — no diffing of participant
  sets. Cache is private (holds GUIDs).

## Folded-in Codex PR #1 fixes

| Codex | Issue | Resolution here |
|---|---|---|
| P1 | path matching used display nickname vs site names | matching is full-name; nicknames applied only at alias stage |
| P2 | draw cache keyed by tournament only → wrong bracket for 2nd event | key draw cache by (tournament, event) |
| P2 | round parser merges all match-groups → wrong opponent/time | scoped page gives per-match cards; draw projection only for unscheduled rounds |
| P1 | watcher crashes on naive vs aware datetimes in `_compose_time` | normalize schedule times to tz-aware (or compare naive-to-naive) in the watch path |

## Privacy (unchanged, enforced)

- Public `web/upcoming.json`: GUID-free via `_strip_guids`; friend display names
  via the alias map; opponents verbatim (alias-mapped where a mapping exists).
- Private `data/upcoming_state.json`: retains tournament/player GUIDs for re-fetch;
  gitignored by the public repo.
- `test_privacy_guard` continues to assert no GUID reaches any `web/*.json`.

## Testing strategy

Pure-function unit tests (no network):

- **find:** window filtering (keeps in-range, drops past/far-future); skips
  online-entry links; de-dupes by GUID.
- **match_friends:** accepts surname-first form; accepts all three Chau VN
  spellings; rejects "Chau Vu"/"Quan Chau"; rejects single-token "Toni"/"Matti";
  honors exclude.csv (Yuki Matti, wrong Toni); matches GUID-less Maila/Thy.
- **parse_player_schedule:** pool event → all-scheduled nodes with correct
  court/ISO time/opponent; singles vs doubles opponent extraction; seed markers
  stripped; missing time → `time: None` (not a crash).
- **build precedence:** scheduled node wins; draw projection fills only
  unscheduled rounds; no round double-counted.
- **privacy:** assembled public dict has zero GUID-bearing keys/values.

Live drivers stay `# pragma: no cover`, exercised manually against the real site
(evidence: re-run `badminton upcoming` and confirm Stadin reappears with 8
entries identical to the hand-built file).

## Risks

- **Finder DOM drift** — the finder ignores date params and paginates oddly;
  isolating its parse in a pure function with fixture tests contains the blast
  radius.
- **Ban risk** — mitigated by caps/throttle/cache and by only fetching scoped
  pages for matched friends.
- **Ambiguous full-name hits** (a stranger sharing all tokens) — rare; if it
  occurs the entry is still gated by the confirmed roster, and exclude.csv is the
  escape hatch. Out of scope to auto-resolve; log such collisions.

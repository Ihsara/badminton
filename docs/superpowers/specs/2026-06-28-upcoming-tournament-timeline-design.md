# Upcoming-Tournament Timeline — Design

**Date:** 2026-06-28
**Status:** DESIGNED, not started
**Author:** brainstorming session (Chau + Claude)

## Problem

The tracker only records *past, completed* matches. For an upcoming tournament a
friend is entered in, there is no way to see **when their next match is**, what
court, or the **projected path to the Final** (assuming they keep winning) — the
information needed to plan the day around showing up at the venue.

The single most important piece of info: *"When is my friend's next match, what
time should they be at the venue, and what's the projected time/path to the
final?"*

## Goals

- Show, per tracked friend, a **timeline of upcoming matches up to the Final**,
  with honest, decaying confidence (confirmed time+opponent → estimated →
  projected).
- Surface the **next match prominently** (hero card + countdown + "be there by").
- **Filter to a subset of players** (e.g. just Chau + Vu Luu for a given event).
- **Export to chat-friendly text** with chooseable options.
- Run **live** on the home server, self-pacing the refresh around the tournament
  schedule so it polls hard only when it matters.

## Non-goals (YAGNI / deferred)

- `.ics` calendar export — deferred to a later spec (text export only for now).
- A manual "refresh now" UI button — the scheduler handles freshness; design
  leaves a sentinel-file hook so it's trivial to add later, but it is not built.
- Horizontal full-bracket visualization as the default — a "see full draw"
  zoom-out is explicitly out of scope for v1 (timeline is the view).
- Predicting/inventing future opponents or precise future times.

## Existing architecture (context)

The historical pipeline is untouched:

```
friend GUIDs → fetch.py → workbook (.xlsx) → export.py → web/data.json
                                                  → explorer views (app.js)
```

- `client.py` — Playwright session: nojazz.eu cookie dismissal + login. **Reuse.**
- `search.py` — name→GUID resolution via `/find/player/?q=`. **Reuse.**
- `parse.py` — extracts `.match__row` / `.match__result ul.points` from a
  profile's `/tournaments` page. New parsers mirror this style.
- `config.py` — paths, `BASE_URL`, `EDIT_PASSWORD`. Add new path constants here.
- `aliases.py` — name→display mapping (`data/aliases.csv`). Applied to friends'
  names in the upcoming data too.
- Frontend: vanilla JS, zero-build, hash router in `web/app.js`
  (`viewGroup/viewPlayers/viewTournament/...`), styles in `web/styles.css`.

## Data source facts (tournamentsoftware.com, Finland instance)

No public JSON API — scrape with Playwright. Verified URL/DOM patterns
(see hot-memory `tournamentsoftware-draw-schedule-urls`):

- Tournament = GUID. Order-of-play: `/tournament/{guid}/Matches` and per-day
  `/tournament/{guid}/matches/{YYYYMMDD}`; matches grouped under absolute
  clock-time headers `h5.match-group__header` ("9.30"); court+duration in the
  `.match__header-aside` tooltip `title="Duration: 31m | Hall - K2 ..."`.
- Draw list `/sport/draws.aspx?id={guid}` (`table.ruler`, `td.drawname` links);
  one draw `/sport/draw.aspx?id={guid}&draw={N}` → `/tournament/{guid}/draw/{N}`,
  DOM `div.bracket.js-bracket` > `bracket-round__match-group` per round; round
  headers "Kierros 32/16, Quarter final, Semi final, Final"; Byes explicit;
  inline `la 14.3.2026 9.30` once scheduled.
- States: pre-draw → only entries (`/sport/events.aspx?id={guid}`); post-draw →
  bracket w/ Byes, no times; post-order-of-play → Matches page populated.
- Player upcoming entries appear on `/player-profile/{guid}/tournaments` (same
  `.module--card` / `.match` DOM `parse.py` already reads) with a future date.
- **Politeness:** serial requests + small delays, one reused session — a prior
  community scraper was IP-banned for aggressive scraping.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Scope | **Both halves end-to-end**: live scraper + visualization. |
| What to track | **Auto from profiles** — any confirmed friend with a future-dated entry. |
| Refresh cadence | **Self-paced** — scraper derives next-refresh delay from tournament dates/times. |
| Opponent privacy | **Public draw = public data** — reproduce opponent names verbatim; **no GUIDs** in the public file. Friends' own names go through aliases. |
| View placement | **Both** — always-present "Upcoming" tab AND home-page takeover during an active window. |
| Visualization | **Vertical timeline** of match cards (phone-first), not a horizontal bracket. |
| Filter | Player-subset chips; view + export respect the selection. |
| Export | **Chat-friendly plaintext** (copy to clipboard), with chooseable options. |
| Export options | which players · how far ahead · detail level · which tournament. |

## Architecture

```
                        EXISTING (historical) — untouched
  friend GUIDs → fetch.py → workbook → export.py → web/data.json
                        NEW (upcoming)
  friend GUIDs → upcoming_fetch.py ─┐
                                    ├→ upcoming_build.py → web/upcoming.json (public, GUID-free)
  draw + order-of-play pages ───────┘                  → data/upcoming_state.json (private, holds GUIDs)
                                    ▲
            upcoming_schedule.py decides WHEN to run next (self-paced loop)
```

### New modules (one purpose each)

- **`upcoming_fetch.py`** — scrape upcoming data. Reuses `client.py` session,
  `search.py`. Three sub-extractors over saved-HTML-testable pure parsers:
  - `find_upcoming_entries(profile_html)` → which tournaments/events a friend is
    entered in with a future date.
  - `parse_draw(draw_html)` → bracket rounds + slots + inline scheduled times.
  - `parse_order_of_play(matches_html)` → per-match clock time + court.
- **`upcoming_build.py`** — assemble the **path** per friend/event and emit the
  GUID-free public `web/upcoming.json` (aliases applied to friends' names); write
  the private `data/upcoming_state.json` (with GUIDs) for re-fetch. Atomic write
  (temp + rename); never publish a half-scraped file.
- **`upcoming_schedule.py`** — pure function `next_refresh_delay(state, now)` →
  seconds; plus the `--watch` loop driver.
- **`upcoming_export.py`** (or a frontend-only function) — the chat-text
  formatter. Pure function over the `upcoming.json` structure + options.
- CLI verb in `__main__.py`: `uv run badminton upcoming [--watch]`.

### Data model — `web/upcoming.json`

```jsonc
{
  "generated_at": "2026-03-13T20:05:00+02:00",
  "next_refresh_hint": "2026-03-14T08:30:00+02:00",
  "tournaments": [
    {
      "name": "Stadin Mestaruuskilpailut",
      "venue": "Valkeavuoren liikuntahalli",
      "start_date": "2026-03-14", "end_date": "2026-03-15",
      "status": "order_published",   // entries | draw_published | order_published | finished
      "entries": [
        {
          "player": "Chau",          // alias-applied friend name
          "event": "MS B",           // category + level
          "path": [
            { "round": "R16", "state": "done",
              "opponent": "Some Name", "result": "W 21-15 21-12",
              "court": "K2", "time": "2026-03-14T09:30:00+02:00" },
            { "round": "QF", "state": "scheduled",
              "opponent": "Real Opponent", "court": "K3",
              "time": "2026-03-14T13:30:00+02:00", "time_kind": "not_before" },
            { "round": "SF", "state": "projected",
              "opponent": "Winner of QF2", "day": "2026-03-15", "session": "afternoon" },
            { "round": "Final", "state": "projected",
              "opponent": null, "day": "2026-03-15" }
          ]
        }
      ]
    }
  ]
}
```

- **No tournament/profile GUIDs in this public file.** GUIDs live only in the
  private `data/upcoming_state.json`.
- **Three path states** drive all UI:
  - `done` — result known; muted; shows W/L + score.
  - `scheduled` — real opponent + court + time; `time_kind` ∈ {`exact`,
    `not_before`}.
  - `projected` — generic opponent label ("Winner of QF2") or null; **day or
    session only**, never a precise time; never an invented name.

### Self-pacing scheduler

`next_refresh_delay(state, now)` (pure, unit-tested):

| Situation derived from scraped dates/times | Next refresh |
|---|---|
| No tracked tournament within ~7 days | once daily |
| Tournament ≤ 3 days away, draw not published | every ~6h |
| Draw/order published, match day is today | every ~20–30 min |
| A tracked friend's match within ~2h | every ~10–15 min |
| Friend's last match of the day done, or tournament finished | back off to daily |

`--watch` loops: scrape → build → write → sleep until hint. Wakes early if a
sentinel file exists (hook for a future manual-refresh button; not built now).

### Deployment (home server)

- Runs as a second always-on supervised command in the existing Docker container
  (`uv run badminton upcoming --watch`), inheriting `.env`/auth. Regenerated
  `upcoming.json` lands on the mounted `./web` for publishing, exactly like
  `data.json` today.
- On scrape failure: log, keep serving the last good `upcoming.json`, retry on
  next scheduled tick. Never publish partial data.

## Visualization (`web/app.js` + `web/styles.css`)

New route `#/upcoming` → `viewUpcoming()`; always-present "Upcoming" nav tab.
Home `viewGroup()` leads with a condensed "Next up" hero when a tournament is in
its active window (reverts automatically otherwise).

Phone-first **vertical timeline**, top→bottom = current round → Final:

- **Pinned hero "Next match" card**: player · round · opponent (or "Winner of
  QF1") · court · time (with "Not Before" when applicable) · live countdown ·
  "be at venue by ~HH:MM".
- **Timeline cards**, one per round, with a **"you are here" divider** between
  current and projected.
- **Confidence decays visibly**: `done` muted (result), `scheduled` solid card,
  `projected` dashed/lighter with generic opponent + day/session only.
- **Round color-coding** (R16→QF→SF→Final escalating accent).
- Semantic nested lists; reuse existing `styles.css` idiom; no framework.

### Filter + Export bar (top of view)

- **Player filter** — chips to narrow to a subset; view + export both respect it.
- **Export panel** with options: ✅ which players · ✅ how far ahead (next match
  only ↔ full path to final) · ✅ detail level (court / opponent / be-there time /
  projected markers) · ✅ which tournament. Action: **"Copy for chat"** →
  clipboard plaintext, e.g.:

```
🏸 Stadin · Sat 14 Mar
Chau (MS B): QF ~13:30 Court K3 vs Real Opponent
Vu Luu (WD B): R32 ~10:15 Court K5
(projected → SF Sat afternoon)
```

The formatter is a pure function over `upcoming.json` + options — unit-testable.

## Testing strategy

- **Pure parsers** (`find_upcoming_entries`, `parse_draw`,
  `parse_order_of_play`, path-builder, `next_refresh_delay`, text formatter) →
  unit tests over saved HTML fixtures / dicts, **no network**. TDD.
- Thin Playwright `goto` layer is the only network-touching code; kept minimal.
- Verify-before-completion: hit `/api/health`, generate a sample `upcoming.json`
  from a real upcoming entry (Stadin), screenshot the timeline before claiming
  done.

## Privacy checklist (rule #4)

- `upcoming.json` contains **no profile/tournament GUIDs** (grep before publish).
- GUIDs live only in `data/upcoming_state.json` (private repo, never `git add`ed
  to the public repo).
- Friends' own names pass through `aliases.csv`; opponent names from the public
  draw are reproduced verbatim (already-public info).
- Before any public push: `git ls-files | grep -E 'data/|\.env'` empty, and
  `upcoming.json` GUID-free.

## Open questions for implementation

- Exact "be at venue by" lead time (suggest configurable, default 30 min before
  earliest of `not_before`/exact).
- Session boundaries for `projected` day-only nodes ("morning/afternoon") — derive
  from the day's earliest/latest scheduled times if available, else omit session.
- How rounds map to labels across draw sizes (R32/R16/QF/SF/F) — normalize in the
  path-builder from the site's round headers.

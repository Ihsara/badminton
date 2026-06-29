# Live auto-recheck + readable "next match" view — design

**Date:** 2026-06-29
**Status:** PLANNED, not started
**Branch (design):** `feat/live-upcoming-next-match`

## Problem

The upcoming-tournament pipeline (merged in PR #3) scrapes a tournament's
scoped player pages into `web/upcoming.json` and renders a timeline. Two gaps
remain for the friend group's day-of-tournament use:

1. **It is not actually live for the tracked tournament.** `docker-compose.yml`
   runs `badminton upcoming --watch`, but with **no `--tournament` flag**, so the
   watcher only sees auto-discovered tournaments. The Stadin tournament
   (`1A563200-14BA-4328-955A-922A5EEC6374`) is outside the auto-discovery window,
   so the always-on watcher currently refreshes *nothing* for it. The refreshed
   file is also never pushed to the public site automatically.
2. **The next opponent is not easy to read at a glance.** The timeline view is
   rich but per-event; there is no single "who does each friend play next, and
   when" summary, and no link out to the tournament's own page.

The user's goal: *get the next opponent as fast as possible, see it easily, with
a link, and keep it as up-to-date as possible.*

**Hard constraint — fully unattended.** The user will be away from the home-server
machine during the tournament. Every part of this must run automatically, survive
reboots, and **degrade gracefully** (never wedge, never silently go stale) with no
human present. This rules out any "run a .bat by hand" or "re-login when prompted"
step in the live path.

## Goals

- Make the always-on watcher track the Stadin tournament and refresh on a tight
  cadence near match time.
- Auto-publish the refreshed `web/upcoming.json` to the public site without
  putting GitHub push credentials inside the scraper container.
- Add a readable per-player "next match" summary block with a clickable
  tournament link.
- Keep an open browser tab live without manual reload.

## Non-goals

- No change to how matches are scraped/parsed (PR #3 covers that).
- No new identity/discovery work (multi-nickname matching is tracked separately).
- No general tournament-admin UI; this is read-only display.

## Decisions (locked with user)

- **Auto-recheck:** wire the Docker watcher to the Stadin GUID; auto-publish via
  the existing host-side redeploy pattern (not from inside the container).
- **Refresh floor:** 5 min when a friend's match is < 2h away; 10 min on match
  day. (Down from 15 / 30.)
- **Readable view:** per-player "next match" summary block + clickable tournament
  link; link is general (renders for whatever tournaments are in the file).
- **Tournament GUID is public.** Narrow the public-file GUID stripping to
  player/profile GUIDs only; keep `tournament_guid` so the link works on GitHub
  Pages too. Player/profile GUIDs are still always stripped.
- **Browser poll:** an open timeline tab re-fetches `upcoming.json` every 2 min
  and re-renders if `generated_at` changed.

## Architecture / changes

### A. Cadence (`src/badminton_tracker/upcoming_schedule.py`) — pure, TDD

`next_refresh_delay(state, now)` constants change:

| Situation                          | Before  | After   |
| ---------------------------------- | ------- | ------- |
| Friend match ≤ 2h away             | 15 min  | **5 min**  |
| Match day, order published         | 30 min  | **10 min** |
| Tournament ≤ 3 days out            | 6 h     | 6 h     |
| Otherwise                          | daily   | daily   |

New constants `FIVE_MIN = 300`, `TEN_MIN = 600`; `FIFTEEN_MIN` / `THIRTY_MIN`
removed. The imminent-match window stays `0 <= secs <= 7200` (2h). Logic
otherwise unchanged. The watch loop and politeness model are unchanged — one
scoped page hit per friend per refresh.

### B. Watcher wiring (`docker-compose.yml`)

The `upcoming` service command gains the Stadin GUID:

```yaml
command: ["uv", "run", "badminton", "upcoming", "--watch",
          "--tournament", "1A563200-14BA-4328-955A-922A5EEC6374"]
```

`--tournament` is already supported and is `append`, so auto-discovery still runs
for every other tournament; the GUID just guarantees Stadin is always scoped.
The GUID is a public tournament identifier, so it is fine to commit in compose.

#### B2. Unattended resilience for the watcher (TDD where pure)

The watcher must survive a multi-day unattended run. Two concrete fixes:

- **Persist the auth cookie across restarts.** The `upcoming` compose service
  currently mounts only `./data` and `./web`, so `out/auth_state.json`
  (`STATE_FILE`) is lost on every container restart and the scraper re-logs in
  from scratch each time (wasteful, ban-risk). Add an `./out:/app/out` mount to
  the `upcoming` service so the saved session persists. `ensure_login` already
  re-auths from `.env` creds and re-saves the state when the cookie goes stale —
  with the mount, that refreshed cookie now survives restarts.
- **Never crash-loop on a transient failure.** `ensure_login` raises on login
  failure and `watch()` does not catch it, so one bad refresh would bubble out and
  (under Docker `restart: unless-stopped`) hammer the login endpoint in a tight
  restart loop. Wrap each `run_once()` in `watch()` so an exception is logged and
  the loop simply waits for the next cadence tick (back off to the `SIX_HOURS`
  delay after a failure so a persistent outage does not spin). The last good
  `web/upcoming.json` stays in place, so the site degrades to "slightly stale,"
  never to "broken." The failure-backoff branch of `watch()` is covered by a test
  via an injected `run_once` that raises.

### C. Auto-publish (host, runs as Ihsara)

A new `windows/publish-upcoming.bat` mirroring `windows/redeploy.bat`'s shape:

- If `web/upcoming.json` has uncommitted changes (or differs from
  `origin/main`), `git add web/upcoming.json && git commit && git push origin
  main` **as the Ihsara account** (same identity the existing publish flow uses).
- Run the privacy gate first as a guard: abort the push if the file contains any
  player/profile GUID (defense in depth — the assembler already strips them).
- Register it as a **scheduled task** in `windows/install-autostart.ps1` next to
  the existing redeploy task (every ~5 min). Because the user is away, publishing
  must be a registered task that runs unattended on a timer — never a `.bat` the
  user double-clicks. The task must be self-contained: log to a file, swallow
  transient git/network errors, and simply try again next tick.

Push credentials and the Ihsara identity stay on the host; the container only
writes the file via the `./web` mount. This preserves CLAUDE.md rules #4 and #5.

**Interaction with `redeploy.bat` (must not wedge while away).** Pages deploys
from `main` on `web/**` changes, and the home server's `redeploy.bat` pull-CD
also tracks `main`. The existing `publish.bat` already commits `web/data.json`
straight onto local `main` and pushes — so committing `upcoming.json` onto `main`
follows the established pattern. The publish task commits **locally first, then
pushes**, so its own commit leaves `HEAD == origin/main` and `redeploy.bat` sees
"nothing to do" (no rebuild loop from our data commits). The one failure mode is
*divergence*: if an unrelated code push advances `origin/main` while the home
server has an unpushed local data commit, `redeploy.bat` refuses the non-ff pull
and leaves the running server up (its documented safe behaviour). To stay
graceful while the user is away, the publish task must itself:
  - pull `--ff-only` before committing; if that fails (diverged), **log and skip
    this tick** rather than force anything — never `reset --hard`, never
    `push --force`;
  - scope every `git add` to exactly `web/upcoming.json` (never `-A`).
In normal tournament operation the home server is the only writer of `main`, so
divergence should not arise; this is purely the graceful-degradation guard.

> **Registration caveat (unattended).** Per the existing memory note
> *CD redeploy needs admin*, scheduled-task registration needs an elevated
> PowerShell. Registering this task is a **one-time setup step done while the
> user is still present**; once registered it runs unattended. The spec/plan must
> call this out explicitly so the live path itself needs no elevation.

### D. Privacy narrowing (`src/badminton_tracker/upcoming_build.py`) — TDD

`_GUID_KEYS` changes from
`("tournament_guid", "player_guid", "guid", "profile_guid")`
to `("player_guid", "profile_guid", "guid")` — i.e. **keep `tournament_guid`,
keep stripping every player/profile GUID.**

- New test: `assemble_upcoming` output **retains** `tournament_guid` and
  **drops** `player_guid`/`profile_guid`/`guid` on a nested fixture.
- The privacy-gate command in the task/CLAUDE docs is updated: the public file
  may now contain exactly one GUID shape *only* as a `tournament_guid` value; the
  player-leak check becomes "no `player_guid`/`profile_guid` keys and no profile
  GUID values." A test encodes this so CI enforces it.
- CLAUDE.md rule #4 gets a one-line clarification: tournament GUIDs are public;
  profile/player GUIDs are the secret.

### E. Readable "next match" block (`web/app.js`, `web/styles.css`) — JS

Pure helper `nextMatchPerPlayer(upc)` → `[{player, event, node, tournament}]`,
one row per player = their earliest `state === "scheduled"` node, sorted by time.

- Rendered as a table at the top of `viewUpcoming()`:
  `player · HH:MM · round · vs opponent · event`.
- Per-tournament header carries the link:
  `https://<base>/tournament/<tournament_guid>/` (built from the now-public
  `tournament_guid`; if absent, no link — graceful).
- "updated N min ago" from `generated_at`.
- Compact one-liner version reused in the homepage takeover.

`base` is the public site host (`badmintonfinland.tournamentsoftware.com`),
hardcoded as a constant in `app.js` (it is already public and fixed).

### F. Browser poll (`web/app.js`) — JS

A single module-level interval (cleared/re-armed like `__upcTimers`): every
120 s, re-fetch `upcoming.json`; if `generated_at` differs from the loaded copy,
update `UPC` and re-render the current view. Only active while the Upcoming view
is mounted, to avoid background fetches on other pages.

## Data flow

```
tournamentsoftware  --(scrape, every 5min near match)-->  container: run_upcoming
   --> web/upcoming.json (host, via ./web mount; GUID-narrowed, player-GUID-free)
   --(host scheduled task, as Ihsara, privacy-gated)-->  git push origin main
   --> GitHub Pages redeploy
open browser tab  --(poll every 2min)-->  ./upcoming.json  --> re-render if changed
```

## Error handling (must be graceful — nobody is watching)

- Watcher: `run_upcoming` tolerates the cookie wall and empty results; **`watch()`
  now also catches any exception from a refresh**, logs it, and backs off to the
  6h delay rather than crash-looping (B2). A stale cookie is auto-refreshed from
  `.env` by `ensure_login`; the refreshed cookie persists via the new `./out`
  mount. Worst case is a slightly-stale file, never a wedged container.
- Publish task: offline/failed `git push` is logged and retried next tick (mirrors
  `redeploy.bat`); privacy-gate failure aborts the push and logs loudly. A push
  failure never blocks the next refresh.
- Browser poll: a failed fetch is swallowed; the last good `UPC` stays rendered;
  the interval keeps trying.
- **No path requires human intervention to recover** from a transient failure;
  each component self-heals on its next tick.

## Testing

- `next_refresh_delay`: 5-min imminent, 10-min match-day, 6h near, daily idle —
  red/green per case.
- `assemble_upcoming`: keeps `tournament_guid`, strips player/profile GUIDs.
- Privacy: a test asserting the public assembler never emits a player/profile
  GUID value (regression guard for the narrowed strip list).
- Manual verification: `/api/health`, then load the Upcoming view and confirm the
  summary block + working tournament link + "updated N ago"; observe one poll
  cycle re-render. Evidence before claiming done (CLAUDE.md rule #6).

## Rollout

Split into **code** (shippable via the normal PR flow) and **one-time host setup**
(must be done while the user is present, since it needs elevation).

1. **Code (PR):** land A + B2 + D + E + F with tests; data already present. CI
   green, merge to main → existing CD redeploys the home server automatically.
2. **Compose (PR):** update `docker-compose.yml` (B: Stadin GUID + `./out` mount)
   and add `windows/publish-upcoming.bat` (C) + its registration block in
   `install-autostart.ps1`.
3. **One-time host setup (while present):** rebuild (`windows\start.bat`),
   register the publish scheduled task in an **elevated** PowerShell (per the
   *CD-redeploy-needs-admin* memory note). Verify `/api/health`, confirm the
   watcher logs a refresh, and confirm the publish task pushes a changed
   `upcoming.json`. After this, the whole loop runs unattended.

Once step 3 is done, the user can leave: the container auto-restarts on
boot/crash, refreshes every 5 min near match time, auto-refreshes its cookie,
auto-publishes, and the open tab self-updates — all self-healing.

# Bracket Visualization (sub-project B) — Design

**Date:** 2026-07-01
**Status:** Approved (brainstorming Task 1 of the bracket-visualization plan).
**Plan:** [`docs/superpowers/plans/2026-07-01-bracket-visualization.md`](../plans/2026-07-01-bracket-visualization.md)

## Goal

A private, edit-password-gated **"Archive"** view in the home-server web app that
renders a tournament's draws — elimination draws as left→right bracket trees,
group/round-robin draws as W–L standings tables — reading sub-project A's already
-shipped `/api/archive/*` endpoints. The only backend change is enriching the
`/bracket` payload with player display names. The public pipeline
(`build.py`/`export.py`/`web/data.json`/`web/upcoming.json`) stays byte-for-byte
untouched.

## Scope (v1 — "one thing done well")

Lean: render elimination draws correctly, drill down tournament → draws, highlight
the friend group's slots, render group draws as standings, and handle empty/error
states. **Not in v1:** connector lines between bracket rounds, point/set-diff
standings columns.

Two decisions from the brainstorming session change the plan's original defaults:
1. **Group draws → standings table** (was: simple match list).
2. **Court/time subtext** added to match boxes (was: not shown).

## Privacy (Global Constraint — rule #4)

The archive holds profile GUIDs and full rosters. This view is **PRIVATE**: gated
behind the edit password (same posture as the Maintain tab), served only by the
home server. Archive data is fetched at runtime via the authed API and is **never
baked into a committed file** — nothing from the archive is written into
`web/data.json`/`web/upcoming.json` or committed to the public repo.

## Components

| Component | Responsibility |
|-----------|----------------|
| `web/archive.js` (new) | The whole B frontend: password gate, tournament-list fetch/render, bracket + standings render, hash routing, mount/teardown. One focused file. |
| `web/index.html` (modify) | "Archive" nav entry + empty `#archive` container, wired the same way as existing views. |
| `web/styles.css` (modify) | Bracket columns, match box, winner + friend highlights, standings table. |
| `src/badminton_tracker/server.py` (modify) | Two small authed additions: (1) `/bracket` payload gains `side1`/`side2` (`{id,name}` arrays) alongside the existing raw id arrays (kept for back-compat); (2) a `GET /api/archive/core-names` route returning `{"names": [...]}` (the public `CORE_NICKNAMES` set) so the frontend can highlight friend slots. |
| `tests/test_archive_endpoints.py` (modify) | Assert the bracket payload carries player names. |
| `tests/fixtures/archive/seed_demo.py` + `tests/test_archive_viz_seed.py` (new) | Seed a realistic multi-round elimination bracket into a temp DB (the live archive is empty) + smoke test. |

## Data flow

1. User opens Archive → enters edit password (held in `sessionStorage`, mirroring
   `maintain.js`).
2. `GET /api/archive/tournaments?password=…` → tournament list (year desc). Empty →
   friendly empty-state. 401/403 → "Wrong edit password."
3. Click a tournament (`#archive/{id}`) → `GET /api/archive/tournament/{id}/bracket`.
4. For each draw:
   - **Elimination:** group matches by `round_index` (sorted **descending** so
     earliest rounds are leftmost, Final rightmost), sort each column by `position`,
     render match boxes.
   - **Group / round-robin (`round_index == 99`):** render a **standings table**.

All fetches happen at runtime. No archive payload is ever persisted client-side or
committed.

## Match box contents

- **Names:** both sides; a side's players joined by `" / "` (doubles). Empty side → `—`.
- **Winner highlight:** the side matching `winner_side` (1|2) is bolded with a
  highlighted background.
- **Score:** `score_raw` (e.g. `"21-15 21-18"`) shown when present; blank when null
  (A defers many real scores — must render gracefully).
- **Court/time:** small muted subtext under the score, **only when**
  `scheduled_iso`/`court` are present. Hidden entirely when null (keeps boxes clean).
- **Walkover / unplayed:** when `winner_side` is null (and/or a side is empty),
  render a `—`/`WO`/`TBD` marker instead of looking broken.
- **Friend highlight:** any slot whose name (case-insensitive) is in the public
  **`CORE_NICKNAMES`** list (the 11 nicknames shipped for the "The Bros" tiering)
  gets a `slot--friend` accent. Kept **visually distinct from the winner highlight**
  — a friend can lose a match, and both states can apply to the same slot.
  `CORE_NICKNAMES` is a Python constant (`core_group.py`), so it is **not reachable
  client-side**; a tiny authed endpoint exposes it (see below), and `archive.js`
  fetches it once on unlock.

## Group / round-robin standings (`round_index == 99`)

A table per group draw: **Played / Won / Lost** per player/pair, **sorted by wins
descending**. Computed client-side from that draw's matches using `winner_side`
alone (no score parsing — `score_raw` is frequently null). A player/pair appears as
a row for every side they occupy; a match with a null `winner_side` counts as
Played for both sides but a win for neither. Renders gracefully when a draw has a
single match.

## Layout & navigation

- Classic left→right elimination tree, rounds as columns (Final rightmost). No
  connector lines in v1 (spacing/columns convey the tree). Wide brackets scroll
  horizontally (`overflow-x: auto`).
- Tournament picker (`/tournaments` list) → click → that tournament's draws
  rendered (elimination trees + group standings), with a "← all tournaments" back
  link. Hash-routed `#archive` / `#archive/{id}`, mirroring the explorer's existing
  view/route convention (READ `app.js`/`maintain.js`; do not invent a new scheme).

## Auth

Reuses the server's existing `_check_password` / `EDIT_PASSWORD` posture and the
frontend password-entry pattern from `maintain.js`. No new auth scheme.

## Error / empty states

- Archive empty (current live reality) → "The archive is empty…" message, not an error.
- Wrong password → password form re-shown with "Wrong edit password."
- Tournament has no draws / not found → readable error, back link intact.

## Testing

The live archive is **empty** (A's historical-discovery gap), so B is built and
tested against the **Task 3 seed fixture** (a Quarter→Semi→Final elimination
ladder with names, winners, scores). Backend shape verified via pytest;
UI verified via the dev-browser skill against the seeded DB (screenshots — evidence
before success claims, rule #6). Final deploy verifies the empty-state renders live
and a seeded bracket renders end-to-end.

## Out of scope (deferred)

- Rendering real captured tournaments (gated on A's historical-discovery follow-up).
- Connector lines between bracket rounds.
- Point/set-difference standings columns (score_raw too often null to be reliable).
- Any change to the public snapshot pipeline.

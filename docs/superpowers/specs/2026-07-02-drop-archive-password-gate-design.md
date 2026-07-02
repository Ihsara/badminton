# Drop the Archive password gate (local / shared-only) — design

**Date:** 2026-07-02
**Status:** DESIGN, approved — ready for implementation plan.
**Origin:** `context/prompts/archive-drop-password-gate.md` (planned, self-contained).

## Problem

The Archive view is edit-password gated: a frontend password form, a
`?password=` query on every `/api/archive/*` call, and a server-side
`_check_password` on each archive route. But the archive is **only ever served
by the always-on home server** (`localhost:8000`) — never on the public GitHub
Page (static host, no backend), and the private data lives only in `data/`.
When access is already restricted to "local machine, or whoever you deliberately
share the home server with" (LAN / a tunnel behind its own auth), the per-view
password is redundant friction. Chau wants it removed for that local/shared use.

This is **home-server ergonomics, not a data or privacy change**. The archive
data stays private by *where it is served* (backend-only, private `data/`), not
by an in-app password.

## Decisions (locked with Chau)

1. **Access boundary** = network reach. The home server is only reachable on
   localhost/LAN (or a tunnel behind its own auth). No in-app gate replaces it.
2. **Full removal** of the password from the archive **GET** routes — delete the
   `_check_password` calls (and the frontend password form / stash), not just
   make them optional.
3. **Frontend goes straight to the tournament list** when `window.MAINT` is
   present — no password form, no unlock button.
4. **EDIT endpoints stay gated.** `POST /api/nicknames` and
   `POST /api/upload-excel` still call `_check_password` — they mutate data, so
   their auth boundary is unchanged. `_check_password` itself is KEPT.
5. **Public-snapshot guard stays.** `web/archive.js`'s `window.MAINT`-absent
   branch ("Archive is off here") is untouched — the public build still fully
   hides the archive.

## Scope

### Server — `src/badminton_tracker/server.py`

Remove the `_check_password(password)` call and the now-unused `password`
parameter from the three archive **GET** routes:

- `GET /api/archive/tournaments`
- `GET /api/archive/core-names`
- `GET /api/archive/tournament/{tid}/bracket`

Keep `_check_password` and `_writes_enabled` — still used by the POST routes.
The mutation auth boundary is unchanged.

### Frontend — `web/archive.js` (all changes contained in this one file)

- `viewArchive`: keep the `!window.MAINT` guard (public snapshot → "Archive is
  off here"). When `window.MAINT` is present and no `id`, render the tournament
  list directly instead of the password form.
- **Delete**: `renderArchivePasswordForm`, `archPass()`, `loadArchive`, and the
  `sessionStorage("archivePw")` stash.
- `ensureFriendSet(pw)` → `ensureFriendSet()`: fetch
  `/api/archive/core-names` with no `?password=`. Its existing degrade-to-empty-
  set-on-failure behavior stays (highlight is a nice-to-have, not load-bearing).
- `fetchArchiveTournaments` / `fetchArchiveBracket`: drop the `?password=` query
  and the `"auth"` / 401-403 return path (GETs can no longer 401).
- `loadTournamentPayload`: drop the `pw` local; call `ensureFriendSet()` and
  `fetchArchiveBracket(id)`.
- `archBracketError`: remove the `payload === "auth"` branch (no longer reachable).
- New default flow: `viewArchive` → `fetchArchiveTournaments()` →
  `renderArchiveList(list)`, with a null/network-failure fallback that reuses the
  existing empty-state markup (a short "couldn't reach the archive" message), NOT
  the deleted password form.

## Tests / verification (TDD)

### `tests/test_archive_endpoints.py`

- **Remove** `test_tournaments_requires_password` and
  `test_core_names_requires_password` — that boundary no longer exists on GETs.
- **Change** `test_tournaments_lists_with_password`,
  `test_bracket_includes_player_names`, `test_core_names_returns_core_set` to
  call the endpoints **without** a `password` param and assert 200 / correct body.
- Keep the `_client` helper (it still sets `EDIT_PASSWORD`, harmless, and builds
  the DB fixture the GET tests reuse).
- **Add** a test that the EDIT endpoints still **401 without a password** — e.g.
  `POST /api/nicknames` (and/or `POST /api/upload-excel`) returns 401/403 when no
  password is supplied. Locks the unchanged mutation boundary.

### Privacy re-confirm (rule #4)

- `test_no_archive_import_in_public_pipeline` and
  `test_public_jsons_contain_no_profile_guids` stay green (untouched).
- `git status --porcelain web/` shows no data leak; public build still hides the
  archive.

### Manual

- On `localhost:8000` the Archive view opens with **no password prompt** and
  lists the tournaments/events; friend-highlight still works.
- On the public snapshot it still says "Archive is off here".

## Constraints

uv-only, ruff clean, TDD, **no `Co-Authored-By`**. Backend + private frontend
only; public `web/data.json` / site untouched. The data stays private by where
it is served, not by the in-app password.

## Out of scope (YAGNI)

- No tunnel-layer auth (Cloudflare Access / Tailscale ACL) work — the network
  boundary is assumed to already be the operator's responsibility.
- No changes to EDIT-endpoint auth, the crawler, or the public pipeline.

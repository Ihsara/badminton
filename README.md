# Badminton Bro Tracker

Tracks our friend group's match results from
[badmintonfinland.tournamentsoftware.com](https://badmintonfinland.tournamentsoftware.com)
and produces a match log + statistics in the format of
`data/Badminton Bro Tournament Log v2.xlsx`.

## Rules (hard)

- Managed and run with **uv** (`pyproject.toml`, `uv run …`).
- Linted with **ruff** (`uv run ruff check`).
- All statistics are computed in **Python** — no spreadsheet formulas.

## Setup

```bash
uv sync                       # install deps (Playwright, openpyxl, …)
uv run playwright install chromium   # one-time browser download
cp .env.example .env          # then fill in credentials (already done locally)
```

Credentials live in `.env` (git-ignored): `TOURNAMENTSOFTWARE_USERNAME`,
`TOURNAMENTSOFTWARE_PASSWORD`, `TOURNAMENTSOFTWARE_BASE_URL`.

## Workflow

1. **Discover the friend group** — snowballs the match graph from your profile,
   resolves each name to a profile GUID, and writes `players.csv`:

   ```bash
   uv run badminton discover --depth 2
   ```

   This writes two files:
   - `players.csv` — one row per friend (from the workbook), with a best-guess
     `profile_guid` and a `confidence` column (`high` / `low` / `none`).
   - `players_candidates.csv` — every player discovered in the match graph, as a
     lookup table for filling blanks.

2. **Confirm `players.csv`** — open it and, for each real friend, put `Y` in the
   `include` column. Eyeball the `low`-confidence guesses, and paste a
   `profile_guid` for anyone left blank (grab it from their `/player-profile/<guid>`
   URL on the site, or from `players_candidates.csv`).

3. **Build outputs** — fetches every included player, deduplicates shared matches,
   and writes the log, computed stats, and refreshes the explorer:

   ```bash
   uv run badminton build
   ```

   Outputs (in `out/`, git-ignored):
   - `matches.csv` — one row per match, source-workbook column order.
   - `Badminton Bro Tournament Log - generated.xlsx` — `Data`,
     `Player statistics`, and `Tournament statistics` sheets (values, not formulas).

## The explorer + always-on server

A zero-build static web app in `web/` reads `web/data.json` — group standings,
per-player profiles, head-to-head, and tournament pages. The deployment server
also lets the group **edit from the browser**: Santeri replaces the Excel and
friends fix nicknames, each change validated in Python and git-committed.

```bash
uv run badminton export    # rebuild web/data.json (alias-aware) from the workbook
uv run badminton server    # full app + edit API at http://localhost:8000
uv run badminton serve     # static-only explorer (no editing)
```

Set `BADMINTON_EDIT_PASSWORD` in `.env` to enable the **Maintain** tab.

### Deployment & sharing

This packages into a home container + a public GitHub Pages snapshot, with all
personal data kept in a private nested repo. See **[SETUP.md](SETUP.md)** for the
Windows autostart, the Ihsara public/private repo split, and publishing.

- **Home (you):** `windows\start.bat` (Docker) — always-on, full data + editing.
- **Friends:** the public Pages URL — sanitized snapshot, falls back to "offline"
  if a live tunnel is configured but down.

## Names & nicknames

`data/aliases.csv` maps each name in the log to a friendly display nickname. It
auto-fills with the group and is editable in the **Maintain** tab — every edit is
committed, so history is never lost. The mapping that ties a nickname to a real
name + profile GUID stays in the **private** `players.csv`; it never reaches the
public `data.json`.

One exception to "no GUIDs in public files": the **tournament** GUID is a public
event identifier (the tournament's own page id on tournamentsoftware.com) and is
deliberately kept in `web/upcoming.json` so the UI can link out with an "open on
tournamentsoftware" link. Player and profile GUIDs are still always stripped.

## Layout

```
src/badminton_tracker/
  client.py     login + cookie-consent handling + session reuse
  search.py     resolve display names -> profile GUIDs
  parse.py      extract match rows from a /player-profile/{guid}/tournaments page
  discover.py   snowball friend discovery -> players.csv
  fetch.py      fetch + dedupe all confirmed players' matches
  stats.py      per-player / per-tournament aggregates (Python, not Excel formulas)
  build.py      write matches.csv + generated .xlsx + the CSV match-log mirror
  excel_source.py  read the source workbook (schema, friend names, match rows)
  aliases.py    name -> nickname mapping (data/aliases.csv), applied on export
  export.py     build web/data.json (sanitized, alias-aware)
  validate.py   security + format checks for uploads / nickname edits
  versioning.py commit each data change to the private data/ repo
  server.py     FastAPI app: explorer + /api/upload-excel + /api/nicknames
  serve.py      static-only explorer server
  __main__.py   `badminton` CLI

web/            zero-build explorer (index.html, app.js, maintain.js, config.js, styles.css)
data/           PRIVATE nested repo: Excel, players.csv, aliases.csv  (gitignored here)
windows/        start/stop/publish .bat + autostart PowerShell
Dockerfile, docker-compose.yml   home-server container (restart: unless-stopped)
```

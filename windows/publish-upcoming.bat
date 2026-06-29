@echo off
REM ---------------------------------------------------------------------------
REM Unattended publish of the live upcoming.json to the PUBLIC repo (Ihsara).
REM Runs on a schedule (see install-autostart.ps1). Graceful by design:
REM   - pulls --ff-only first; if branches diverged it SKIPS (never forces),
REM   - privacy-gates the file (aborts on any player/profile GUID leak),
REM   - stages ONLY web/upcoming.json, commits + pushes, retries next tick.
REM Requires: host authenticated as Ihsara for origin (see SETUP.md).
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0\.."

REM Nothing changed? exit quietly.
git diff --quiet -- web/upcoming.json
if %errorlevel%==0 (
  echo [pub-upc] no change; nothing to do.
  exit /b 0
)

REM Privacy gate: abort if any GUID that isn't a tournament_guid is present.
~\.local\bin\uv.exe run python -c "import json,re,sys; b=open('web/upcoming.json',encoding='utf-8').read(); d=json.loads(b); g=set(re.findall(r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}',b)); tg={t.get('tournament_guid') for t in d['tournaments']}; leak=g-tg; sys.exit(1 if (leak or 'player_guid' in b or 'profile_guid' in b) else 0)"
if %errorlevel% neq 0 (
  echo [pub-upc] PRIVACY GATE FAILED - refusing to publish. Resolve by hand.
  exit /b 1
)

REM Fast-forward only; if diverged, skip this tick (graceful, never force).
git fetch origin main 1>nul 2>nul
git merge --ff-only origin/main 1>nul 2>nul
if %errorlevel% neq 0 (
  echo [pub-upc] local and origin/main diverged; skipping this tick.
  exit /b 0
)

git add web/upcoming.json
git commit -m "data: live upcoming.json refresh" 1>nul 2>nul
git push origin main
if %errorlevel% neq 0 (
  echo [pub-upc] push failed ^(offline?^); will retry next run.
  exit /b 0
)
echo [pub-upc] published upcoming.json.
endlocal
exit /b 0

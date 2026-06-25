@echo off
REM Publish the current (sanitized) snapshot to the PUBLIC repo / GitHub Pages.
REM Refreshes web\data.json from the workbook, commits it to the PUBLIC repo,
REM and pushes to the Ihsara remote. The private data\ repo is never pushed here.
REM
REM Requires: you are authenticated as Ihsara for the public remote (see SETUP.md).
cd /d "%~dp0\.."
echo Refreshing the public snapshot...
uv run badminton export
git add web/data.json
git commit -m "Publish snapshot %DATE% %TIME%" || echo (nothing changed)
echo Pushing to the public (Ihsara) remote...
git push origin main
echo Done. GitHub Pages will redeploy in a minute.
pause

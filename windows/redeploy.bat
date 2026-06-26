@echo off
REM ---------------------------------------------------------------------------
REM Pull-based continuous deployment for the home server.
REM
REM Runs on a schedule (see install-autostart.ps1). On each run it:
REM   1. fetches origin/main and exits immediately if there is nothing new
REM      (no rebuild, no Docker churn when the code hasn't changed),
REM   2. fast-forwards to the new code,
REM   3. rebuilds + restarts the container,
REM   4. health-checks /api/health and, if it does not come up, ROLLS BACK to
REM      the previous commit so a bad push can't leave the site dead.
REM
REM Only fast-forward pulls are taken: if local and origin/main have diverged
REM (e.g. a local publish.bat commit vs. an upstream code push), it refuses and
REM leaves the running server untouched for a human to resolve.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0\.."

git fetch origin main 1>nul 2>nul
if %errorlevel% neq 0 (
  echo [redeploy] git fetch failed ^(offline?^); will retry next run.
  exit /b 0
)

for /f %%i in ('git rev-parse HEAD') do set "BEFORE=%%i"
for /f %%i in ('git rev-parse origin/main') do set "REMOTE=%%i"

if "%BEFORE%"=="%REMOTE%" (
  echo [redeploy] up to date ^(%BEFORE:~0,7%^); nothing to do.
  exit /b 0
)

echo [redeploy] new code %BEFORE:~0,7% -^> %REMOTE:~0,7%; deploying...

git merge --ff-only origin/main
if %errorlevel% neq 0 (
  echo [redeploy] local and origin/main diverged; cannot fast-forward.
  echo [redeploy] leaving the running server as-is. Resolve by hand.
  exit /b 1
)

docker compose up -d --build
if %errorlevel% neq 0 (
  echo [redeploy] build/start failed; rolling back to %BEFORE:~0,7%.
  git reset --hard %BEFORE%
  docker compose up -d --build
  exit /b 1
)

REM Health gate: poll /api/health for up to ~60s (12 x 5s).
set "HEALTHY="
for /l %%n in (1,1,12) do (
  if not defined HEALTHY (
    curl -fs http://localhost:8000/api/health >nul 2>&1 && set "HEALTHY=1"
    if not defined HEALTHY timeout /t 5 /nobreak >nul
  )
)

if not defined HEALTHY (
  echo [redeploy] health check FAILED after deploy; rolling back to %BEFORE:~0,7%.
  git reset --hard %BEFORE%
  docker compose up -d --build
  exit /b 1
)

echo [redeploy] deployed %REMOTE:~0,7% and healthy.
endlocal
exit /b 0

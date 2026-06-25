@echo off
REM Start (or rebuild + start) the always-on Badminton Bros server.
cd /d "%~dp0\.."
echo Starting Badminton Bros...
docker compose up -d --build
if %errorlevel% neq 0 (
  echo.
  echo Failed to start. Is Docker Desktop running?
  pause
  exit /b 1
)
echo.
echo Running at http://localhost:8000
echo (Use windows\stop.bat to stop, or windows\install-autostart.ps1 to autostart on login.)

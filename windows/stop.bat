@echo off
REM Stop the Badminton Bros server.
cd /d "%~dp0\.."
docker compose down
echo Stopped.

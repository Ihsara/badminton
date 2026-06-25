@echo off
REM Fallback if you don't want Docker: run the server directly with uv.
REM Requires uv installed on Windows (https://docs.astral.sh/uv/) and a .env file.
cd /d "%~dp0\.."
echo Starting Badminton Bros (no Docker)...
uv sync
uv run badminton server --host 0.0.0.0 --port 8000
pause

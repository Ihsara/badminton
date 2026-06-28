"""Paths and environment configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

BASE_URL = os.environ.get(
    "TOURNAMENTSOFTWARE_BASE_URL", "https://badmintonfinland.tournamentsoftware.com"
).rstrip("/")
USERNAME = os.environ.get("TOURNAMENTSOFTWARE_USERNAME", "")
PASSWORD = os.environ.get("TOURNAMENTSOFTWARE_PASSWORD", "")

DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(exist_ok=True)

STATE_FILE = OUT_DIR / "auth_state.json"
# Private data lives in the nested git repo under data/.
PLAYERS_CSV = DATA_DIR / "players.csv"
ALIASES_CSV = DATA_DIR / "aliases.csv"
SOURCE_XLSX = DATA_DIR / "Badminton Bro Tournament Log v2.xlsx"
# Human-readable CSV mirror of the workbook's Data sheet — committed beside the
# binary .xlsx so `git -C data diff` shows row-level deltas.
MATCHES_MIRROR_CSV = DATA_DIR / "matches_mirror.csv"

# Upcoming-tournament pipeline (parallel to the historical one).
# Public, GUID-free artifact served beside data.json:
UPCOMING_JSON = ROOT / "web" / "upcoming.json"
# Private re-fetch state (holds tournament/profile GUIDs) — lives in data/ repo:
UPCOMING_STATE_JSON = DATA_DIR / "upcoming_state.json"

# ── Web server / maintenance endpoints ─────────────────────────────────────
# Shared password protecting the write endpoints (Excel upload, alias edits).
# Empty string disables writes entirely (read-only deployment).
EDIT_PASSWORD = os.environ.get("BADMINTON_EDIT_PASSWORD", "")
# Hard limit for uploaded workbooks (bytes). Defends the upload endpoint.
MAX_UPLOAD_BYTES = int(os.environ.get("BADMINTON_MAX_UPLOAD_BYTES", str(8 * 1024 * 1024)))

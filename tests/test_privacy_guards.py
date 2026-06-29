# tests/test_privacy_guards.py
"""Rule #4 enforcement: no GUIDs / person_ids may reach public web/*.json."""
from __future__ import annotations

import re

import pytest

from badminton_tracker.config import ROOT, UPCOMING_JSON

GUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
PERSON_ID_RE = re.compile(r'"person_id"')
PUBLIC_FILES = [ROOT / "web" / "data.json", UPCOMING_JSON]


@pytest.mark.parametrize("path", PUBLIC_FILES, ids=lambda p: p.name)
def test_public_json_has_no_guid(path):
    if not path.exists():
        pytest.skip(f"{path.name} not generated in this environment")
    text = path.read_text(encoding="utf-8")
    leaked = GUID_RE.findall(text)
    assert not leaked, f"{path.name} leaks profile GUID(s): {leaked[:3]}"


@pytest.mark.parametrize("path", PUBLIC_FILES, ids=lambda p: p.name)
def test_public_json_has_no_person_id(path):
    if not path.exists():
        pytest.skip(f"{path.name} not generated in this environment")
    text = path.read_text(encoding="utf-8")
    assert not PERSON_ID_RE.search(text), f"{path.name} leaks a person_id field"


def test_assemble_upcoming_strips_tournament_and_player_guids():
    from badminton_tracker.upcoming_build import assemble_upcoming

    raw = {
        "tournaments": [
            {
                "name": "T",
                "tournament_guid": "1A563200-14BA-4328-955A-922A5EEC6374",
                "venue": "",
                "start_date": "2026-07-04",
                "end_date": "2026-07-04",
                "status": "order_published",
                "entries": [
                    {
                        "player": "Chau",
                        "player_guid": "d69f71b9-69f2-472e-97b2-4fc80ac43a17",
                        "event": "MD",
                        "path": [{"round": "R1", "opponent": "X", "state": "scheduled"}],
                    }
                ],
            }
        ]
    }
    pub = assemble_upcoming(raw, {}, "2026-06-28T00:00:00+03:00")
    blob = repr(pub).lower()
    assert "1a563200" not in blob
    assert "d69f71b9" not in blob

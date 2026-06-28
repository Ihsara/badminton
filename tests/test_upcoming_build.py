# tests/test_upcoming_build.py
from __future__ import annotations

from badminton_tracker.upcoming_build import assemble_upcoming


def test_assemble_strips_guids_and_applies_aliases():
    raw = {
        "tournaments": [{
            "name": "Stadin", "tournament_guid": "AAAA1111-2222-3333-4444-555566667777",
            "venue": "Hall", "start_date": "2026-03-14", "end_date": "2026-03-15",
            "status": "order_published",
            "entries": [{
                "player": "Chau's Partner", "player_guid": "BBBB...",
                "event": "WD B",
                "path": [{"round": "R32", "state": "scheduled", "opponent": "Some Pair",
                          "court": "K5", "time": "2026-03-14T10:15:00+02:00",
                          "time_kind": "exact", "guid": "NESTED-GUID-SENTINEL"}],
            }],
        }]
    }
    alias_map = {"Chau's Partner": "Bonnie"}
    out = assemble_upcoming(raw, alias_map, "2026-03-13T20:00:00+02:00")

    blob = repr(out)
    assert "AAAA1111" not in blob  # tournament guid stripped
    assert "player_guid" not in blob  # player guid stripped
    assert "NESTED-GUID-SENTINEL" not in blob  # guid inside path[] (list->dict) stripped
    assert out["tournaments"][0]["entries"][0]["player"] == "Bonnie"  # alias applied
    assert out["generated_at"] == "2026-03-13T20:00:00+02:00"


def test_assemble_keeps_opponent_names_verbatim():
    raw = {"tournaments": [{"name": "T", "tournament_guid": "G", "venue": "",
            "start_date": "2026-03-14", "end_date": "2026-03-14",
            "status": "order_published",
            "entries": [{"player": "Chau", "player_guid": "X", "event": "MS B",
                "path": [{"round": "QF", "state": "scheduled", "opponent": "Real Opponent",
                          "court": "K1", "time": None, "time_kind": None}]}]}]}
    out = assemble_upcoming(raw, {}, "2026-03-13T20:00:00+02:00")
    assert out["tournaments"][0]["entries"][0]["path"][0]["opponent"] == "Real Opponent"

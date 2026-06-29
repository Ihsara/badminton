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
    assert "AAAA1111-2222-3333-4444-555566667777" in blob  # tournament guid is PUBLIC, kept
    assert out["tournaments"][0]["tournament_guid"] == "AAAA1111-2222-3333-4444-555566667777"
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


def test_assemble_never_leaks_player_or_profile_guid():
    raw = {"tournaments": [{
        "name": "T", "tournament_guid": "1A563200-14BA-4328-955A-922A5EEC6374",
        "venue": "", "start_date": "2026-07-04", "end_date": "2026-07-04",
        "status": "order_published",
        "entries": [{
            "player": "Chau", "player_guid": "PLAYER-GUID-SENTINEL",
            "profile_guid": "PROFILE-GUID-SENTINEL", "event": "MS B",
            "path": [{"round": "R1", "state": "scheduled", "opponent": "X",
                      "court": None, "time": None, "time_kind": None,
                      "guid": "NESTED-GUID-SENTINEL"}],
        }],
    }]}
    out = assemble_upcoming(raw, {}, "2026-07-04T08:00:00+03:00")
    blob = repr(out)
    assert "PLAYER-GUID-SENTINEL" not in blob
    assert "PROFILE-GUID-SENTINEL" not in blob
    assert "NESTED-GUID-SENTINEL" not in blob
    assert "player_guid" not in blob and "profile_guid" not in blob
    # tournament guid is allowed through:
    assert out["tournaments"][0]["tournament_guid"] == "1A563200-14BA-4328-955A-922A5EEC6374"

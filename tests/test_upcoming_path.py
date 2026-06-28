# tests/test_upcoming_path.py
from __future__ import annotations

from badminton_tracker.upcoming_path import build_path, normalize_round


def test_normalize_round_maps_named_rounds():
    assert normalize_round("Quarter final") == "QF"
    assert normalize_round("Semi final") == "SF"
    assert normalize_round("Final") == "Final"


def test_normalize_round_maps_finnish_and_numeric():
    assert normalize_round("Kierros 16") == "R16"
    assert normalize_round("Round of 32") == "R32"


def test_build_path_marks_scheduled_node():
    rounds = [
        {"round_label": "Quarter final", "slots": ["Chau", "Real Opponent"],
         "scheduled_iso": "2026-03-14T13:30:00+02:00"},
        {"round_label": "Semi final", "slots": ["Winner", "Bye"], "scheduled_iso": None},
        {"round_label": "Final", "slots": [], "scheduled_iso": None},
    ]
    schedule = [
        {"event": "MS B", "round_label": "Quarter final", "time": "13.30",
         "court": "K3", "players": ["Chau", "Real Opponent"], "date": "2026-03-14",
         "result": None},
    ]
    path = build_path(rounds, schedule, "Chau", "MS B", "2026-03-14")
    qf = next(n for n in path if n["round"] == "QF")
    assert qf["state"] == "scheduled"
    assert qf["opponent"] == "Real Opponent"
    assert qf["court"] == "K3"


def test_build_path_marks_done_node_with_result():
    rounds = [{"round_label": "Quarter final", "slots": ["Chau", "Beaten Foe"],
               "scheduled_iso": "2026-03-14T09:30:00+02:00"}]
    schedule = [{"event": "MS B", "round_label": "Quarter final", "time": "9.30",
                 "court": "K2", "players": ["Chau", "Beaten Foe"],
                 "date": "2026-03-14", "result": "W 21-15 21-12"}]
    path = build_path(rounds, schedule, "Chau", "MS B", "2026-03-14")
    assert path[0]["state"] == "done"
    assert path[0]["result"] == "W 21-15 21-12"


def test_build_path_projects_future_round_with_generic_opponent():
    rounds = [
        {"round_label": "Quarter final", "slots": ["Chau", "Real Opponent"],
         "scheduled_iso": "2026-03-14T13:30:00+02:00"},
        {"round_label": "Semi final", "slots": [], "scheduled_iso": None},
    ]
    schedule = [{"event": "MS B", "round_label": "Quarter final", "time": "13.30",
                 "court": "K3", "players": ["Chau", "Real Opponent"],
                 "date": "2026-03-14", "result": None}]
    path = build_path(rounds, schedule, "Chau", "MS B", "2026-03-14")
    sf = next(n for n in path if n["round"] == "SF")
    assert sf["state"] == "projected"
    assert sf["opponent"] == "Winner of QF"
    assert sf["time"] is None  # never a precise time for projected

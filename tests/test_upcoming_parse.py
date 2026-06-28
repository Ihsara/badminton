from __future__ import annotations

from pathlib import Path

from badminton_tracker.upcoming_parse import parse_draw, parse_order_of_play

FIX = Path(__file__).parent / "fixtures" / "upcoming"


def _read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_parse_draw_returns_round_labels_in_order():
    rounds = parse_draw(_read("draw_knockout.html"))
    assert [r["round_label"] for r in rounds] == ["Quarter final", "Semi final", "Final"]


def test_parse_draw_extracts_slot_names():
    rounds = parse_draw(_read("draw_knockout.html"))
    qf = rounds[0]
    assert qf["slots"] == ["Chau", "Real Opponent"]


def test_parse_draw_keeps_bye_verbatim():
    rounds = parse_draw(_read("draw_knockout.html"))
    sf = rounds[1]
    assert "Bye" in sf["slots"]


def test_parse_draw_reads_inline_scheduled_iso():
    rounds = parse_draw(_read("draw_knockout.html"))
    assert rounds[0]["scheduled_iso"] == "2026-03-14T13:30:00+02:00"


def test_parse_draw_final_with_no_players_has_empty_slots():
    rounds = parse_draw(_read("draw_knockout.html"))
    assert rounds[2]["slots"] == []


def test_order_of_play_groups_by_time():
    rows = parse_order_of_play(_read("order_of_play.html"), "2026-03-14")
    assert [r["time"] for r in rows] == ["9.30", "13.30"]


def test_order_of_play_extracts_court():
    rows = parse_order_of_play(_read("order_of_play.html"), "2026-03-14")
    assert rows[0]["court"] == "K2"
    assert rows[1]["court"] == "K5"


def test_order_of_play_splits_event_and_round():
    rows = parse_order_of_play(_read("order_of_play.html"), "2026-03-14")
    assert rows[0]["event"] == "MS B"
    assert rows[0]["round_label"] == "Quarter final"


def test_order_of_play_lists_players():
    rows = parse_order_of_play(_read("order_of_play.html"), "2026-03-14")
    assert rows[0]["players"] == ["Chau", "Real Opponent"]

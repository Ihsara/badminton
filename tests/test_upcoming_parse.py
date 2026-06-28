from __future__ import annotations

from pathlib import Path

from badminton_tracker.upcoming_parse import parse_draw

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

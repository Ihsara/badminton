from pathlib import Path

from badminton_tracker import archive_parse

FIX = Path(__file__).parent / "fixtures" / "archive"


def test_parse_draw_list():
    html = (FIX / "draw_list.html").read_text(encoding="utf-8")
    draws = archive_parse.parse_draw_list(html)
    names = [d["name"] for d in draws]
    assert "Men's Doubles" in names and "Women's Singles" in names
    assert all(d["id"] for d in draws)


def test_parse_bracket_final_with_winner():
    html = (FIX / "bracket_elimination.html").read_text(encoding="utf-8")
    matches = archive_parse.parse_bracket(html)
    assert len(matches) == 1
    m = matches[0]
    assert m["round_label"] == "Final"
    assert m["round_index"] == 0
    assert m["score_raw"] is None
    assert m["winner_side"] == 1
    side_names = [[p["name"] for p in side] for side in m["sides"]]
    assert side_names == [["Alice Smith"], ["Bob Jones"]]

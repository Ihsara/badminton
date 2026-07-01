from pathlib import Path

from badminton_tracker import archive_parse
from badminton_tracker.archive_parse import _round_index

FIX = Path(__file__).parent / "fixtures" / "archive"


def test_parse_draw_list():
    html = (FIX / "draw_list.html").read_text(encoding="utf-8")
    draws = archive_parse.parse_draw_list(html)
    names = [d["name"] for d in draws]
    assert "Men's Doubles" in names and "Women's Singles" in names
    assert all(d["id"] for d in draws)


def test_parse_matches_page_singles_final_with_score_and_winner():
    html = (FIX / "matches_page.html").read_text(encoding="utf-8")
    matches = archive_parse.parse_matches_page(html)
    final = next(m for m in matches if m["round_label"] == "Final")
    assert final["draw_id"] == "AAAA1111-1111-1111-1111-111111111111:16"
    assert final["draw_name"] == "MS C"
    assert final["round_index"] == 0
    assert final["position"] == 0
    assert [[p["name"] for p in s] for s in final["sides"]] == [["Alpha One"], ["Beta Two"]]
    assert final["sides"][1][0]["seed"] == 3            # "[3/4]" -> first number
    assert final["sides"][0][0]["profile_guid"] == "AAAA1111-1111-1111-1111-111111111111:9"
    assert final["winner_side"] == 2
    assert final["score_raw"] == "10-21 6-21"           # side1-side2 per game


def test_parse_matches_page_doubles_semi_two_players_side1_wins():
    html = (FIX / "matches_page.html").read_text(encoding="utf-8")
    matches = archive_parse.parse_matches_page(html)
    semi = next(m for m in matches if m["round_label"] == "Semi final")
    assert semi["round_index"] == 1
    assert [len(s) for s in semi["sides"]] == [2, 1]     # side1 doubles, side2 single (fixture)
    assert [p["name"] for p in semi["sides"][0]] == ["Alpha One", "Gamma Three"]
    assert semi["winner_side"] == 1
    assert semi["score_raw"] == "21-15 21-18"


def test_round_index_orders_real_labels():
    """_round_index must produce the correct finals-first ordering for real site labels."""
    assert _round_index("Final") == 0
    assert _round_index("Semi final") == 1
    assert _round_index("Semifinal") == 1
    assert _round_index("Semi-final") == 1
    assert _round_index("Quarter final") == 2
    assert _round_index("Quarterfinal") == 2
    assert _round_index("Quarter-final") == 2
    assert _round_index("Round of 16") == 3
    assert _round_index("R16") == 3
    assert _round_index("Round of 32") == 4
    assert _round_index("R32") == 4
    assert _round_index("Round of 64") == 5
    assert _round_index("R64") == 5
    assert _round_index("Preliminary") == 99

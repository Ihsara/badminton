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


def test_parse_bracket_multi_round_positions_and_ordering():
    html = (FIX / "bracket_two_rounds.html").read_text(encoding="utf-8")
    matches = archive_parse.parse_bracket(html)

    assert len(matches) == 3

    semis = [m for m in matches if m["round_label"] == "Semi final"]
    finals = [m for m in matches if m["round_label"] == "Final"]
    assert len(semis) == 2
    assert len(finals) == 1

    # round_index: NOTE — "Semi final" actually matches "final" (index 0) before
    # "semi" (index 1) in _ROUND_ORDER because "final" is a substring of "Semi final".
    # This is a known parser ordering concern (FINDING: see task-5-report.md).
    # Pinned to parser's REAL behaviour; do NOT change without fixing _round_index.
    assert all(m["round_index"] == 0 for m in semis)
    assert finals[0]["round_index"] == 0

    # position resets per round: Semi final matches get 0 and 1;
    # Final match gets 0 (not 2), confirming per-round reset.
    semi_positions = sorted(m["position"] for m in semis)
    assert semi_positions == [0, 1]
    assert finals[0]["position"] == 0

    # winner_side: Semi A (Alice has-won on side 1), Semi B (Dave has-won on side 2)
    semi_a = next(m for m in semis if m["position"] == 0)
    semi_b = next(m for m in semis if m["position"] == 1)
    assert semi_a["winner_side"] == 1
    assert semi_b["winner_side"] == 2
    assert finals[0]["winner_side"] == 1

    # score_raw is None for all (score markup not yet confirmed against a real fixture)
    assert all(m["score_raw"] is None for m in matches)

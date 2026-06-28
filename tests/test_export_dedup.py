"""Tests for match-id generation and conservative duplicate collapsing in export."""

from __future__ import annotations

from badminton_tracker.export import dedupe_matches, match_id


def _m(team1, team2, result, sets, *, date="2026-03-28", tournament="SMASH",
       category="MS", level="B", round_="16"):
    return {
        "date": date,
        "tournament": tournament,
        "category": category,
        "level": level,
        "round": round_,
        "team1": team1,
        "team2": team2,
        "result": result,
        "sets": sets,
    }


# ---- match_id ---------------------------------------------------------------


def test_match_id_is_stable_for_same_match():
    m = _m(["Junya"], ["Dhirav"], "WIN", [[21, 10], [21, 11]])
    assert match_id(m) == match_id(dict(m))


def test_match_id_is_side_independent():
    """The same physical match logged from either side gets the same id."""
    a = _m(["Junya"], ["Dhirav"], "WIN", [[21, 10], [21, 11]])
    b = _m(["Dhirav"], ["Junya"], "LOSS", [[10, 21], [11, 21]])
    assert match_id(a) == match_id(b)


def test_match_id_differs_for_different_brackets():
    a = _m(["Boris", "Khai"], ["Chau", "Nga"], "LOSS", [[14, 21]], level="Rento")
    b = _m(["Boris", "Khai"], ["Chau", "Nga"], "WIN", [[21, 14]], level="Kunto")
    assert match_id(a) != match_id(b)


def test_match_id_differs_for_different_scores():
    a = _m(["Boris", "Khai"], ["Chau", "Nga"], "WIN", [[21, 14]])
    b = _m(["Boris", "Khai"], ["Chau", "Nga"], "WIN", [[21, 18]])
    assert match_id(a) != match_id(b)


# ---- dedupe_matches ---------------------------------------------------------


def test_dedupe_collapses_symmetric_same_score_duplicate():
    a = _m(["Junya"], ["Dhirav"], "WIN", [[21, 10], [21, 11]])
    b = _m(["Dhirav"], ["Junya"], "LOSS", [[10, 21], [11, 21]])
    kept, removed = dedupe_matches([a, b])
    assert len(kept) == 1
    assert len(removed) == 1


def test_dedupe_keeps_different_brackets():
    a = _m(["Boris", "Khai"], ["Chau", "Nga"], "LOSS", [[14, 21]], level="Rento")
    b = _m(["Boris", "Khai"], ["Chau", "Nga"], "WIN", [[21, 14]], level="Kunto")
    kept, removed = dedupe_matches([a, b])
    assert len(kept) == 2
    assert removed == []


def test_dedupe_keeps_real_rematch_with_different_scores():
    """Same pairing, same bracket, but genuinely played twice with different scores."""
    a = _m(["Boris", "Khai"], ["Chau", "Nga"], "WIN", [[21, 14]])
    b = _m(["Boris", "Khai"], ["Chau", "Nga"], "LOSS", [[14, 21]])
    kept, removed = dedupe_matches([a, b])
    assert len(kept) == 2
    assert removed == []


def test_dedupe_preserves_order_and_kept_payloads():
    a = _m(["Junya"], ["Dhirav"], "WIN", [[21, 10]])
    b = _m(["Dhirav"], ["Junya"], "LOSS", [[10, 21]])
    other = _m(["Tong"], ["Maila"], "WIN", [[21, 5]], tournament="Other", round_="F")
    kept, _ = dedupe_matches([a, b, other])
    assert kept[0] is a  # first occurrence wins
    assert other in kept

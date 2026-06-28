"""Tests for match-id generation and conservative duplicate collapsing in export."""

from __future__ import annotations

from badminton_tracker.aliases import apply
from badminton_tracker.export import dedupe_matches, match_id, roster_from_names
from badminton_tracker.stats import player_stats


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


# ---- roster collapse after aliasing -----------------------------------------


def _stat_match(p1, o1):
    """A minimal singles match in the internal (non-payload) shape player_stats reads."""
    return {
        "date": "2026-07-04", "tournament": "Stadin", "category": "WD", "level": "C",
        "round": "Pool", "player_1": p1, "player_2": "", "opponent_1": o1,
        "opponent_2": "", "result": "WIN",
        "set_1_own": 21, "set_1_opp": 10, "set_2_own": 21, "set_2_opp": 12,
        "set_3_own": None, "set_3_opp": None,
    }


def test_aliased_spellings_collapse_to_one_roster_entry():
    """Two raw spellings that alias to the same display name (Thy Nguyen / Thy
    NGUYEN → Thy) must yield ONE stats page, not a duplicate row per spelling.
    Mirrors the dict.fromkeys de-dup in export.export_from_excel."""
    mapping = {"Thy Nguyen": "Thy", "Thy NGUYEN": "Thy"}
    raw_friends = ["Thy Nguyen", "Thy NGUYEN", "Maila"]
    display = list(dict.fromkeys(apply(f, mapping) for f in raw_friends))
    assert display == ["Thy", "Maila"]  # collapsed, order preserved

    matches = [
        {**_stat_match("Thy", "Stranger A")},
        {**_stat_match("Thy", "Stranger B")},
    ]
    stats = player_stats(matches, roster_from_names(display))
    thy_rows = [s for s in stats if s["player"] == "Thy"]
    assert len(thy_rows) == 1
    assert thy_rows[0]["games"] == 2


def test_distinct_person_not_collapsed_by_partial_name():
    """'Thy Le' is a different person from 'Thy' and must NOT be merged."""
    mapping = {"Thy Nguyen": "Thy"}
    display = list(dict.fromkeys(apply(f, mapping) for f in ["Thy Nguyen", "Thy Le"]))
    assert display == ["Thy", "Thy Le"]

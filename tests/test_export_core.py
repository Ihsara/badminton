from __future__ import annotations

from badminton_tracker.export import apply_aliases


def test_apply_aliases_merges_case_only_duplicates():
    matches = [{
        "player_1": "Paphon Kasemvudhi", "player_2": "Paphon KASEMVUDHI",
        "opponent_1": "Maila", "opponent_2": "Tong",
    }]
    # No explicit alias rows; rely on the case-fold merge derived from the names.
    out = apply_aliases(matches, mapping={})
    names = {out[0]["player_1"], out[0]["player_2"]}
    assert names == {"Paphon Kasemvudhi"}  # both spellings collapsed to one


from badminton_tracker.core_group import CORE_NICKNAMES, is_core  # noqa: E402
from badminton_tracker.export import (  # noqa: E402
    build_payload,
    roster_from_names,
)


def test_core_membership_is_case_insensitive():
    assert is_core("Maila") is True
    assert is_core("maila") is True
    assert is_core("Paphon Kasemvudhi") is False


def test_core_group_has_expected_members():
    expected = {"Chau", "Dao", "Santeri", "Thy", "Maila",
                "Tong", "Junya", "Toni", "Matti", "Khai", "Boris"}
    assert {n for n in CORE_NICKNAMES} == expected


def test_build_payload_tags_core_flag():
    matches = [
        {"date": "2026-01-01", "tournament": "T", "category": "MD", "level": "B",
         "round": "R1", "player_1": "Maila", "player_2": "Paphon Kasemvudhi",
         "opponent_1": "X", "opponent_2": "Y",
         "result": "W",
         "set_1_own": 21, "set_1_opp": 10,
         "set_2_own": None, "set_2_opp": None,
         "set_3_own": None, "set_3_opp": None},
    ]
    roster = roster_from_names(["Maila", "Paphon Kasemvudhi"])
    payload = build_payload(matches, roster, source="test")
    by_name = {p["player"]: p for p in payload["players"]}
    assert by_name["Maila"]["core"] is True
    assert by_name["Paphon Kasemvudhi"]["core"] is False

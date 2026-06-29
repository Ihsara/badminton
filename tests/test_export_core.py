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

from __future__ import annotations

from badminton_tracker.aliases import casefold_merge_map


def test_casefold_merge_collapses_allcaps_variant():
    names = ["Paphon Kasemvudhi", "Paphon KASEMVUDHI", "Maila"]
    m = casefold_merge_map(names)
    # Both Paphon spellings map to the proper-case one; Maila (no twin) is absent.
    assert m["Paphon KASEMVUDHI"] == "Paphon Kasemvudhi"
    assert m.get("Paphon Kasemvudhi") in (None, "Paphon Kasemvudhi")
    assert "Maila" not in m


def test_casefold_merge_prefers_more_lowercase_as_canonical():
    names = ["TUOMAS TIAINEN", "Tuomas Tiainen"]
    m = casefold_merge_map(names)
    assert m["TUOMAS TIAINEN"] == "Tuomas Tiainen"


def test_casefold_merge_no_twins_returns_empty():
    assert casefold_merge_map(["Maila", "Tong", "Junya"]) == {}

# tests/test_discovery_queue.py
from __future__ import annotations

from badminton_tracker import discovery_queue as dq


def test_split_known_vs_new():
    sightings = [
        {
            "seen_name": "Santeri",
            "kind": "opponent",
            "where_seen": "Hien's profile",
            "alongside": "Hien",
        },
        {
            "seen_name": "Thy",
            "kind": "opponent",
            "where_seen": "Santeri's profile",
            "alongside": "Santeri",
        },
    ]
    known = {"santeri"}  # Santeri is already a known alias
    known_hits, new = dq.split_sightings(sightings, known, queued_names=set())
    assert [h["seen_name"] for h in known_hits] == ["Santeri"]
    assert [n["seen_name"] for n in new] == ["Thy"]
    assert new[0]["confidence"] == "new"
    assert new[0]["decision"] == ""
    assert new[0]["suggested_person_id"] == ""


def test_split_is_case_insensitive():
    sightings = [{"seen_name": "SANTERI", "kind": "partner", "where_seen": "x", "alongside": "y"}]
    known_hits, new = dq.split_sightings(sightings, {"santeri"}, queued_names=set())
    assert len(known_hits) == 1 and not new


def test_split_dedupes_against_queue_and_within_batch():
    sightings = [
        {"seen_name": "Thy", "kind": "opponent", "where_seen": "a", "alongside": "b"},
        {
            "seen_name": "thy",
            "kind": "partner",
            "where_seen": "c",
            "alongside": "d",
        },  # dup in batch
        {"seen_name": "Tong", "kind": "opponent", "where_seen": "e", "alongside": "f"},
    ]
    known_hits, new = dq.split_sightings(sightings, known_names=set(), queued_names={"tong"})
    # "thy" once (batch dedupe), "Tong" suppressed (already queued)
    assert [n["seen_name"] for n in new] == ["Thy"]


def test_queue_round_trip(tmp_path):
    path = tmp_path / "discovery_candidates.csv"
    rows = [
        {
            "seen_name": "Thy",
            "kind": "opponent",
            "where_seen": "Santeri's profile",
            "alongside": "Santeri",
            "suggested_person_id": "",
            "confidence": "new",
            "decision": "",
        }
    ]
    dq.write_queue(rows, path=path)
    back = dq.load_queue(path=path)
    assert back == rows


def test_load_missing_queue_is_empty(tmp_path):
    assert dq.load_queue(path=tmp_path / "nope.csv") == []


def test_fold_decisions_creates_alias_and_clears_row():
    queue = [
        {"seen_name": "eyyy", "kind": "participant", "where_seen": "Kaarina May 2026",
         "alongside": "", "suggested_person_id": "p001", "confidence": "fuzzy", "decision": "p001"},
        {"seen_name": "Mystery", "kind": "opponent", "where_seen": "x",
         "alongside": "y", "suggested_person_id": "", "confidence": "new", "decision": ""},
    ]
    new_aliases, remaining = dq.fold_decisions(queue, existing_aliases=[])
    assert len(new_aliases) == 1
    a = new_aliases[0]
    assert a["person_id"] == "p001" and a["alias"] == "eyyy"
    assert a["kind"] == "nickname" and a["confidence"] == "confirmed"
    assert a["source_tournament"] == "Kaarina May 2026"
    # Undecided row stays queued; decided row removed.
    assert [r["seen_name"] for r in remaining] == ["Mystery"]


def test_fold_is_idempotent_against_existing_aliases():
    queue = [{"seen_name": "Eyyy", "kind": "participant", "where_seen": "K",
              "alongside": "", "suggested_person_id": "p001",
              "confidence": "fuzzy", "decision": "p001"}]
    existing = [{"person_id": "p001", "alias": "eyyy", "kind": "nickname",
                 "guid": "", "source_tournament": "", "confidence": "confirmed"}]
    new_aliases, remaining = dq.fold_decisions(queue, existing_aliases=existing)
    assert new_aliases == []          # already linked, no duplicate
    assert remaining == []            # still consumed from the queue

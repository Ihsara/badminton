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

"""The name-based discovery review queue (data/discovery_candidates.csv).

Discovery harvests names seen next to confirmed friends (partners/opponents) and
on chosen tournament participant lists. A name already known as an alias is a
silent provenance hit; an unknown name becomes a candidate row the human reviews
and decides (fills `decision` with a person_id). NOTHING auto-links a name to a
person — this is the deliberate guard against the wrong-fuzzy-match class.
"""

from __future__ import annotations

import csv

from .config import DISCOVERY_CANDIDATES_CSV

QUEUE_FIELDS = ["seen_name", "kind", "where_seen", "alongside",
                "suggested_person_id", "confidence", "decision"]


def load_queue(path=None) -> list[dict]:
    path = path or DISCOVERY_CANDIDATES_CSV
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return [{k: (r.get(k) or "").strip() for k in QUEUE_FIELDS} for r in csv.DictReader(f)]


def write_queue(rows, path=None) -> None:
    path = path or DISCOVERY_CANDIDATES_CSV
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=QUEUE_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in QUEUE_FIELDS})


def split_sightings(sightings, known_names, queued_names):
    """Partition sightings into (known_hits, new_candidates).

    known_names / queued_names are sets of LOWERCASED names. A sighting whose
    seen_name is already a known alias is a silent provenance hit; otherwise it
    becomes a new candidate, de-duped against the existing queue and within the
    same batch (both case-insensitive).
    """
    known_hits = []
    new_candidates = []
    batch_seen: set[str] = set()
    for s in sightings:
        name = (s.get("seen_name") or "").strip()
        low = name.lower()
        if not name:
            continue
        if low in known_names:
            known_hits.append(s)
            continue
        if low in queued_names or low in batch_seen:
            continue
        batch_seen.add(low)
        new_candidates.append({
            "seen_name": name,
            "kind": s.get("kind", ""),
            "where_seen": s.get("where_seen", ""),
            "alongside": s.get("alongside", ""),
            "suggested_person_id": "",
            "confidence": "new",
            "decision": "",
        })
    return known_hits, new_candidates

"""Person-centric identity model (PRIVATE files in data/ — never published).

A *person* (people.csv) owns many *aliases* (person_aliases.csv): nicknames,
real names, and any profile GUIDs they registered under across tournaments.
This lets one friend be tracked whether they appear as "Chau", "Long Chau Tran",
or "eyyy", and lets GUID-less friends (e.g. Dao) exist as first-class persons.

Matching is EXACT and case-insensitive — no fuzzy/token auto-linking (that
produced the wrong "Dao = Quinn Dao" mapping). All lookups operate on already-
loaded rows so they stay pure and unit-testable.
"""

from __future__ import annotations

import csv

from .config import PEOPLE_CSV, PERSON_ALIASES_CSV

PEOPLE_FIELDS = ["person_id", "real_name", "has_profile", "notes"]
ALIAS_FIELDS = ["person_id", "alias", "kind", "guid", "source_tournament", "confidence"]


def _load(path, fields) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return [{k: (r.get(k) or "").strip() for k in fields} for r in csv.DictReader(f)]


def _write(rows, path, fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def load_people(path=None) -> list[dict]:
    return _load(path or PEOPLE_CSV, PEOPLE_FIELDS)


def load_person_aliases(path=None) -> list[dict]:
    return _load(path or PERSON_ALIASES_CSV, ALIAS_FIELDS)


def write_people(rows, path=None) -> None:
    _write(rows, path or PEOPLE_CSV, PEOPLE_FIELDS)


def write_person_aliases(rows, path=None) -> None:
    _write(rows, path or PERSON_ALIASES_CSV, ALIAS_FIELDS)


def person_for_name(name: str, aliases=None) -> str | None:
    """Exact, case-insensitive alias → person_id. None if unknown."""
    if not name:
        return None
    aliases = load_person_aliases() if aliases is None else aliases
    target = name.strip().lower()
    for a in aliases:
        if a["alias"].lower() == target:
            return a["person_id"]
    return None


def aliases_for_person(person_id: str, aliases=None) -> list[dict]:
    aliases = load_person_aliases() if aliases is None else aliases
    return [a for a in aliases if a["person_id"] == person_id]


def known_alias_names(aliases=None) -> set[str]:
    aliases = load_person_aliases() if aliases is None else aliases
    return {a["alias"].lower() for a in aliases if a["alias"]}

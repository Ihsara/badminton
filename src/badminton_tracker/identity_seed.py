"""One-time migration: players.csv -> people.csv + person_aliases.csv.

Each existing players.csv row becomes one person (p001, p002, …). The row's
nickname and (when different) full_name become alias rows; the profile_guid
rides on the realname alias. GUID-less friends get has_profile="n" — they are
first-class persons, tracked by name. Review the output before committing it to
the private data/ repo (rule #7).
"""

from __future__ import annotations

import csv

from . import identity
from .config import PEOPLE_CSV, PERSON_ALIASES_CSV, PLAYERS_CSV


def _pid(i: int) -> str:
    return f"p{i:03d}"


def build_seed(player_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    people: list[dict] = []
    aliases: list[dict] = []
    for i, row in enumerate(player_rows, start=1):
        pid = _pid(i)
        nickname = (row.get("nickname") or "").strip()
        full_name = (row.get("full_name") or "").strip()
        guid = (row.get("profile_guid") or "").strip()
        confidence = (row.get("confidence") or "low").strip() or "low"
        real_name = full_name or nickname
        people.append({
            "person_id": pid,
            "real_name": real_name,
            "has_profile": "y" if guid else "n",
            "notes": "",
        })
        seen: set[str] = set()
        if nickname:
            seen.add(nickname.lower())
            aliases.append({"person_id": pid, "alias": nickname, "kind": "nickname",
                            "guid": "", "source_tournament": "", "confidence": confidence})
        if full_name and full_name.lower() not in seen:
            aliases.append({"person_id": pid, "alias": full_name, "kind": "realname",
                            "guid": guid, "source_tournament": "", "confidence": confidence})
    return people, aliases


def _read_players(path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def seed_identity(players_csv=None, people_csv=None, aliases_csv=None) -> tuple[int, int]:
    player_rows = _read_players(players_csv or PLAYERS_CSV)
    people, aliases = build_seed(player_rows)
    identity.write_people(people, path=people_csv or PEOPLE_CSV)
    identity.write_person_aliases(aliases, path=aliases_csv or PERSON_ALIASES_CSV)
    return len(people), len(aliases)

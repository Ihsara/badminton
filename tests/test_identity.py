# tests/test_identity.py
from __future__ import annotations

from badminton_tracker import identity


def _seed(tmp_path):
    people = tmp_path / "people.csv"
    aliases = tmp_path / "person_aliases.csv"
    identity.write_people(
        [
            {
                "person_id": "p001",
                "real_name": "Long Chau Tran",
                "has_profile": "y",
                "notes": "me",
            },
            {
                "person_id": "p002",
                "real_name": "Chompoonooch Unwong",
                "has_profile": "n",
                "notes": "Dao",
            },
        ],
        path=people,
    )
    identity.write_person_aliases(
        [
            {
                "person_id": "p001",
                "alias": "Chau",
                "kind": "nickname",
                "guid": "",
                "source_tournament": "",
                "confidence": "high",
            },
            {
                "person_id": "p001",
                "alias": "Long Chau Tran",
                "kind": "realname",
                "guid": "d69f71b9-69f2-472e-97b2-4fc80ac43a17",
                "source_tournament": "",
                "confidence": "high",
            },
            {
                "person_id": "p001",
                "alias": "eyyy",
                "kind": "nickname",
                "guid": "",
                "source_tournament": "Kaarina May 2026",
                "confidence": "confirmed",
            },
            {
                "person_id": "p002",
                "alias": "Dao",
                "kind": "nickname",
                "guid": "",
                "source_tournament": "",
                "confidence": "high",
            },
        ],
        path=aliases,
    )
    return people, aliases


def test_round_trip_people(tmp_path):
    people, _ = _seed(tmp_path)
    rows = identity.load_people(path=people)
    assert len(rows) == 2
    assert rows[0]["person_id"] == "p001"
    assert rows[1]["has_profile"] == "n"  # GUID-less person is first-class


def test_person_for_name_is_case_insensitive_and_multi_nickname(tmp_path):
    _, aliases = _seed(tmp_path)
    al = identity.load_person_aliases(path=aliases)
    assert identity.person_for_name("Chau", al) == "p001"
    assert identity.person_for_name("LONG CHAU TRAN", al) == "p001"  # case-insensitive
    assert identity.person_for_name("eyyy", al) == "p001"  # same person, third nickname
    assert identity.person_for_name("Dao", al) == "p002"
    assert identity.person_for_name("nobody", al) is None


def test_aliases_for_person(tmp_path):
    _, aliases = _seed(tmp_path)
    al = identity.load_person_aliases(path=aliases)
    names = {a["alias"] for a in identity.aliases_for_person("p001", al)}
    assert names == {"Chau", "Long Chau Tran", "eyyy"}


def test_known_alias_names_lowercased(tmp_path):
    _, aliases = _seed(tmp_path)
    al = identity.load_person_aliases(path=aliases)
    assert identity.known_alias_names(al) == {"chau", "long chau tran", "eyyy", "dao"}


def test_load_missing_returns_empty(tmp_path):
    assert identity.load_people(path=tmp_path / "nope.csv") == []
    assert identity.load_person_aliases(path=tmp_path / "nope.csv") == []

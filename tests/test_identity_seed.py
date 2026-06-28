# tests/test_identity_seed.py
from __future__ import annotations

from badminton_tracker import identity_seed

PLAYER_ROWS = [
    {"nickname": "Chau", "full_name": "Long Chau Tran",
     "profile_guid": "d69f71b9-69f2-472e-97b2-4fc80ac43a17", "confidence": "low"},
    {"nickname": "Dao", "full_name": "Chompoonooch Unwong",
     "profile_guid": "", "confidence": "high"},
    {"nickname": "Hien Köhler", "full_name": "Hien Köhler",
     "profile_guid": "215c485f-ed48-4a86-8148-512d35849392", "confidence": "high"},
]


def test_build_seed_one_person_per_row_with_ids():
    people, _ = identity_seed.build_seed(PLAYER_ROWS)
    assert [p["person_id"] for p in people] == ["p001", "p002", "p003"]
    assert people[0]["real_name"] == "Long Chau Tran"


def test_build_seed_guid_presence_sets_has_profile():
    people, _ = identity_seed.build_seed(PLAYER_ROWS)
    assert people[0]["has_profile"] == "y"   # has GUID
    assert people[1]["has_profile"] == "n"   # Dao, GUID-less, first-class
    assert people[2]["has_profile"] == "y"


def test_build_seed_aliases_nickname_and_realname():
    _, aliases = identity_seed.build_seed(PLAYER_ROWS)
    p001 = [a for a in aliases if a["person_id"] == "p001"]
    by_text = {a["alias"]: a for a in p001}
    assert set(by_text) == {"Chau", "Long Chau Tran"}
    assert by_text["Chau"]["kind"] == "nickname"
    assert by_text["Long Chau Tran"]["kind"] == "realname"
    # The GUID rides on the realname alias only.
    assert by_text["Long Chau Tran"]["guid"] == "d69f71b9-69f2-472e-97b2-4fc80ac43a17"
    assert by_text["Chau"]["guid"] == ""


def test_build_seed_dedupes_when_nickname_equals_fullname():
    _, aliases = identity_seed.build_seed(PLAYER_ROWS)
    p003 = [a for a in aliases if a["person_id"] == "p003"]
    # "Hien Köhler" nickname == full_name -> exactly one alias row.
    assert len(p003) == 1
    assert p003[0]["alias"] == "Hien Köhler"


def test_seed_identity_writes_both_files(tmp_path):
    import csv
    players = tmp_path / "players.csv"
    with open(players, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["nickname", "full_name", "profile_guid",
                                          "profile_url", "confidence", "include"])
        w.writeheader()
        for r in PLAYER_ROWS:
            w.writerow({**r, "profile_url": "", "include": ""})
    people_csv = tmp_path / "people.csv"
    aliases_csv = tmp_path / "person_aliases.csv"
    n_people, n_aliases = identity_seed.seed_identity(
        players_csv=players, people_csv=people_csv, aliases_csv=aliases_csv)
    assert n_people == 3
    assert n_aliases == 5  # Chau(2) + Dao(2) + Hien(1)
    assert people_csv.exists() and aliases_csv.exists()

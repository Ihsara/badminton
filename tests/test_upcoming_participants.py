from badminton_tracker.upcoming_participants import match_friends, parse_participants

ROSTER = [
    {"nickname": "Maila", "full_name": "Maila Kataja"},
    {"nickname": "Chau", "full_name": "Long Chau Tran"},
    {"nickname": "Toni", "full_name": "Toni Seppälä"},
    {"nickname": "Junya", "full_name": "Junya Iwata"},
]


def test_parse_participants_extracts_name_and_number():
    html = (
        '<a href="/sport/player.aspx?id=G&player=517">Kataja, Maila</a>'
        '<a href="/sport/player.aspx?id=G&player=476">Iwata, Junya</a>'
    )
    out = parse_participants(html)
    assert {"name": "Kataja, Maila", "player_no": "517"} in out
    assert {"name": "Iwata, Junya", "player_no": "476"} in out


def test_full_name_match_surname_first():
    parts = [{"name": "Kataja, Maila", "player_no": "517"}]
    hits = match_friends(parts, ROSTER, set())
    assert hits == [{"nickname": "Maila", "full_name": "Maila Kataja", "player_no": "517"}]


def test_chau_vietnamese_name_matches():
    parts = [{"name": "Trần Long Châu", "player_no": "612"}]
    hits = match_friends(parts, ROSTER, set())
    assert len(hits) == 1 and hits[0]["nickname"] == "Chau"


def test_chau_does_not_match_chau_vu():
    parts = [{"name": "Chau Vu", "player_no": "1"}]
    assert match_friends(parts, ROSTER, set()) == []


def test_single_token_does_not_match():
    parts = [{"name": "Toni", "player_no": "9"}]  # bare first name only
    assert match_friends(parts, ROSTER, set()) == []


def test_exclude_blocks_full_name_hit():
    parts = [{"name": "Seppälä, Toni", "player_no": "562"}]
    assert match_friends(parts, ROSTER, {"toni seppälä"}) == []

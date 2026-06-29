from badminton_tracker.upcoming_schedule_parse import parse_player_schedule

DOUBLES = (
    "Round 1\nMD Harraste / Hobby - Group B\n"
    "Nga Pham\nLong Chau Tran\nLasse Hukka\nKaleva Piha\n"
    "H2H\nla 4.7.2026 9.00\nTalihalli"
)
SINGLES = (
    "Round 3\nMS B - Group A\n"
    "Junya Iwata [1]\nJere Filatoff\n"
    "H2H\nla 4.7.2026 15.00\nTalihalli"
)
NO_TIME = (
    "Round 2\nWD C - Group A\n"
    "Maila Kataja [1]\nThy Nguyen\nJoanne Dagupan\nJohanna Lopez\nH2H\nTalihalli"
)


REAL_COURT = (
    "Round 1\nMD Harraste / Hobby - Group B\n"
    "Nga Pham\nLong Chau Tran\nLasse Hukka\nKaleva Piha\n"
    "H2H\nla 4.7.2026 9.00\nK2"
)


def test_doubles_opponent_partner_court_time():
    [n] = parse_player_schedule([DOUBLES], "Long Chau Tran")
    assert n["round"] == "R1"
    assert n["event"] == "MD Harraste / Hobby - Group B"
    assert n["partner"] == "Nga Pham"
    assert n["opponent"] == "Lasse Hukka / Kaleva Piha"
    # The card's last line is the venue name, not a court designator -> no court.
    assert n["court"] is None
    # Helsinki summer offset so cross-timezone countdowns are correct.
    assert n["time"] == "2026-07-04T09:00:00+03:00"
    assert n["state"] == "scheduled"


def test_real_court_id_is_kept():
    [n] = parse_player_schedule([REAL_COURT], "Long Chau Tran")
    assert n["court"] == "K2"


def test_singles_strips_seed_and_names_opponent():
    [n] = parse_player_schedule([SINGLES], "Junya Iwata")
    assert n["opponent"] == "Jere Filatoff"
    assert n["partner"] is None
    assert n["time"] == "2026-07-04T15:00:00+03:00"


def test_missing_time_is_none_not_crash():
    [n] = parse_player_schedule([NO_TIME], "Thy Nguyen")
    assert n["time"] is None
    assert n["opponent"] == "Joanne Dagupan / Johanna Lopez"

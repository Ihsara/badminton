from __future__ import annotations

from pathlib import Path

from badminton_tracker.upcoming_parse import parse_draw, parse_order_of_play

FIX = Path(__file__).parent / "fixtures" / "upcoming"


def _read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_parse_draw_returns_round_labels_in_order():
    rounds = parse_draw(_read("draw_knockout.html"))
    assert [r["round_label"] for r in rounds] == ["Quarter final", "Semi final", "Final"]


def test_parse_draw_extracts_slot_names():
    rounds = parse_draw(_read("draw_knockout.html"))
    qf = rounds[0]
    assert qf["slots"] == ["Chau", "Real Opponent"]


def test_parse_draw_keeps_bye_verbatim():
    rounds = parse_draw(_read("draw_knockout.html"))
    sf = rounds[1]
    assert "Bye" in sf["slots"]


def test_parse_draw_reads_inline_scheduled_iso():
    rounds = parse_draw(_read("draw_knockout.html"))
    assert rounds[0]["scheduled_iso"] == "2026-03-14T13:30:00+02:00"


def test_parse_draw_final_with_no_players_has_empty_slots():
    rounds = parse_draw(_read("draw_knockout.html"))
    assert rounds[2]["slots"] == []


def test_order_of_play_groups_by_time():
    rows = parse_order_of_play(_read("order_of_play.html"), "2026-03-14")
    assert [r["time"] for r in rows] == ["9.30", "13.30"]


def test_order_of_play_extracts_court():
    rows = parse_order_of_play(_read("order_of_play.html"), "2026-03-14")
    assert rows[0]["court"] == "K2"
    assert rows[1]["court"] == "K5"


def test_order_of_play_splits_event_and_round():
    rows = parse_order_of_play(_read("order_of_play.html"), "2026-03-14")
    assert rows[0]["event"] == "MS B"
    assert rows[0]["round_label"] == "Quarter final"


def test_order_of_play_lists_players():
    rows = parse_order_of_play(_read("order_of_play.html"), "2026-03-14")
    assert rows[0]["players"] == ["Chau", "Real Opponent"]


def test_find_upcoming_entries_keeps_future_card():
    from badminton_tracker.upcoming_parse import find_upcoming_entries

    out = find_upcoming_entries(_read("profile_tournaments.html"), "2026-01-01")
    assert len(out) == 1
    e = out[0]
    assert e["tournament"] == "Stadin Mestaruuskilpailut"
    assert e["event"] == "MS B"


def test_find_upcoming_entries_parses_dates_to_iso():
    from badminton_tracker.upcoming_parse import find_upcoming_entries

    out = find_upcoming_entries(_read("profile_tournaments.html"), "2026-01-01")
    assert out[0]["start_date"] == "2026-03-14"
    assert out[0]["end_date"] == "2026-03-15"


def test_find_upcoming_entries_extracts_guid_from_href():
    from badminton_tracker.upcoming_parse import find_upcoming_entries

    out = find_upcoming_entries(_read("profile_tournaments.html"), "2026-01-01")
    assert out[0]["tournament_guid"] == "AAAA1111-2222-3333-4444-555566667777"


def test_find_upcoming_entries_drops_past_card():
    from badminton_tracker.upcoming_parse import find_upcoming_entries

    out = find_upcoming_entries(_read("profile_tournaments.html"), "2027-01-01")
    assert out == []


# ── Live profile DOM (sanitized real snapshot, fake GUIDs) ─────────────────
# The live page differs from the hand-authored fixture: dates live in <time>
# tags, the GUID is in /sport/tournament?id=GUID, one card carries multiple
# events (Luokka:) each with its own draw=N link, and the first card is a
# profile/header card to skip.


def _live() -> list[dict]:
    from badminton_tracker.upcoming_parse import find_upcoming_entries

    return find_upcoming_entries(_read("profile_tournaments_live.html"), "2026-01-01")


def test_live_skips_header_card():
    assert all(e["tournament"] != "Friend Name" for e in _live())


def test_live_card_yields_one_entry_per_event():
    fz = [e for e in _live() if e["tournament"] == "FZ Forza BadU Premier Eliitti"]
    assert {e["event"] for e in fz} == {"WD C", "WS C"}


def test_live_extracts_guid_from_query_string():
    fz = next(e for e in _live() if e["tournament"] == "FZ Forza BadU Premier Eliitti")
    assert fz["tournament_guid"] == "BBBB2222-2222-2222-2222-222222222222"


def test_live_parses_time_tag_date_range():
    fz = next(e for e in _live() if e["tournament"] == "FZ Forza BadU Premier Eliitti")
    assert fz["start_date"] == "2026-05-09"
    assert fz["end_date"] == "2026-05-10"


def test_live_single_time_tag_is_one_day():
    espoo = next(e for e in _live() if e["tournament"] == "Espoo Women's Open 2026")
    assert espoo["start_date"] == espoo["end_date"] == "2026-02-28"


def test_live_extracts_draw_index_per_event():
    by_event = {(e["tournament"], e["event"]): e for e in _live()}
    assert by_event[("FZ Forza BadU Premier Eliitti", "WD C")]["draw_index"] == "19"
    assert by_event[("FZ Forza BadU Premier Eliitti", "WS C")]["draw_index"] == "17"
    assert by_event[("Espoo Women's Open 2026", "WD C")]["draw_index"] == "16"


def test_live_future_filter_keeps_and_drops():
    from badminton_tracker.upcoming_parse import find_upcoming_entries

    html = _read("profile_tournaments_live.html")
    assert len(find_upcoming_entries(html, "2026-01-01")) == 3  # all future of Jan
    assert find_upcoming_entries(html, "2027-01-01") == []  # all past by 2027


def test_old_fixture_still_parsed_via_fallback_with_draw_index_key():
    from badminton_tracker.upcoming_parse import find_upcoming_entries

    out = find_upcoming_entries(_read("profile_tournaments.html"), "2026-01-01")
    assert len(out) == 1
    assert out[0]["event"] == "MS B"
    assert "draw_index" in out[0]  # new key present even on the fallback path

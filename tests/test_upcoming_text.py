from __future__ import annotations

from badminton_tracker.upcoming_text import format_chat_text, next_match_per_player

UPCOMING = {
    "tournaments": [{
        "name": "Stadin", "start_date": "2026-03-14", "end_date": "2026-03-15",
        "entries": [
            {"player": "Chau", "event": "MS B", "path": [
                {"round": "QF", "state": "scheduled", "opponent": "Real Opponent",
                 "court": "K3", "time": "2026-03-14T13:30:00+02:00", "time_kind": "not_before"},
                {"round": "SF", "state": "projected", "opponent": "Winner of QF",
                 "day": "2026-03-15", "session": "afternoon"},
            ]},
            {"player": "Vu Luu", "event": "WD B", "path": [
                {"round": "R32", "state": "scheduled", "opponent": "Some Pair",
                 "court": "K5", "time": "2026-03-14T10:15:00+02:00", "time_kind": "exact"},
            ]},
        ],
    }]
}

PROJECTED_ONLY = {
    "tournaments": [{
        "name": "Stadin", "start_date": "2026-03-14", "end_date": "2026-03-15",
        "entries": [
            {"player": "Chau", "event": "MS B", "path": [
                {"round": "SF", "state": "projected", "opponent": "Winner of QF",
                 "day": "2026-03-15", "session": "afternoon"},
            ]},
        ],
    }]
}


def test_includes_tournament_header():
    out = format_chat_text(UPCOMING, {"horizon": "next", "fields": {"court", "opponent"}})
    assert "Stadin" in out


def test_filters_to_selected_players():
    out = format_chat_text(UPCOMING, {"players": ["Chau"], "horizon": "next",
                                      "fields": {"court", "opponent"}})
    assert "Chau" in out
    assert "Vu Luu" not in out


def test_horizon_next_shows_only_first_unplayed_round():
    out = format_chat_text(UPCOMING, {"players": ["Chau"], "horizon": "next",
                                      "fields": {"court", "opponent"}})
    assert "QF" in out
    assert "SF" not in out  # next-only hides projected rounds


def test_horizon_full_shows_projected_when_requested():
    out = format_chat_text(UPCOMING, {"players": ["Chau"], "horizon": "full",
                                      "fields": {"court", "opponent", "projected"}})
    assert "SF" in out


def test_not_before_time_rendered_with_tilde():
    out = format_chat_text(UPCOMING, {"players": ["Chau"], "horizon": "next",
                                      "fields": {"court", "opponent"}})
    assert "~13:30" in out


def test_court_field_toggle_off_hides_court():
    out = format_chat_text(UPCOMING, {"players": ["Vu Luu"], "horizon": "next",
                                      "fields": {"opponent"}})
    assert "K5" not in out


def test_horizon_full_alone_shows_projected():
    # horizon=="full" surfaces projected rounds even without "projected" in fields.
    out = format_chat_text(UPCOMING, {"players": ["Chau"], "horizon": "full",
                                      "fields": {"court", "opponent"}})
    assert "SF" in out


def test_projected_field_alone_shows_next_projected_when_no_scheduled():
    # In next-mode with no scheduled node, "projected" in fields surfaces the next projected round.
    out = format_chat_text(PROJECTED_ONLY, {"players": ["Chau"], "horizon": "next",
                                            "fields": {"court", "opponent", "projected"}})
    assert "SF" in out


def test_next_mode_hides_projected_when_field_off_and_no_scheduled():
    # Same projected-only entry, but "projected" NOT in fields and horizon=="next" -> hidden.
    out = format_chat_text(PROJECTED_ONLY, {"players": ["Chau"], "horizon": "next",
                                            "fields": {"court", "opponent"}})
    assert "SF" not in out


def _upc():
    return {"tournaments": [{
        "name": "Stadin", "tournament_guid": "1A563200-14BA-4328-955A-922A5EEC6374",
        "entries": [
            {"player": "Chau", "event": "MD Hobby B", "path": [
                {"round": "R1", "state": "scheduled", "opponent": "A / B",
                 "time": "2026-07-04T09:00:00+03:00"},
                {"round": "R2", "state": "scheduled", "opponent": "C / D",
                 "time": "2026-07-04T10:00:00+03:00"}]},
            {"player": "Hien", "event": "WD C", "path": [
                {"round": "R2", "state": "scheduled", "opponent": "E / F",
                 "time": "2026-07-04T10:00:00+03:00"}]},
            {"player": "Done", "event": "MS B", "path": [
                {"round": "R1", "state": "done", "opponent": "G",
                 "time": "2026-07-04T08:00:00+03:00"}]},
        ],
    }]}


def test_next_match_per_player_picks_earliest_scheduled_sorted():
    rows = next_match_per_player(_upc())
    assert [r["player"] for r in rows] == ["Chau", "Hien"]   # sorted by time, Chau 09:00 first
    assert rows[0]["node"]["round"] == "R1"                  # earliest scheduled, not R2
    assert rows[0]["node"]["opponent"] == "A / B"
    assert rows[0]["tournament"] == "Stadin"
    assert rows[0]["tournament_guid"] == "1A563200-14BA-4328-955A-922A5EEC6374"
    assert rows[0]["event"] == "MD Hobby B"


def test_next_match_per_player_omits_players_with_no_scheduled():
    rows = next_match_per_player(_upc())
    assert all(r["player"] != "Done" for r in rows)          # only-done player dropped


def _upc_shared():
    """Two tracked friends (Chau + Vu Luu) partnering each other in the same
    XD match: same tournament, event, time, opponent appears under both
    entries. This is the same physical match listed twice."""
    return {"tournaments": [{
        "name": "Stadin", "tournament_guid": "G",
        "entries": [
            {"player": "Chau", "event": "XD Hobby D", "path": [
                {"round": "R1", "state": "scheduled", "partner": "Vu Luu",
                 "opponent": "Joel / Nargiza", "time": "2026-07-04T16:00:00+03:00"}]},
            {"player": "Vu Luu", "event": "XD Hobby D", "path": [
                {"round": "R1", "state": "scheduled", "partner": "Long Chau Tran",
                 "opponent": "Joel / Nargiza", "time": "2026-07-04T16:00:00+03:00"}]},
        ],
    }]}


def test_next_match_collapses_shared_match_to_one_row_attributed_to_pair():
    rows = next_match_per_player(_upc_shared())
    assert len(rows) == 1                                     # one physical match, one row
    assert rows[0]["player"] == "Chau / Vu Luu"              # both friends, sorted, joined
    assert rows[0]["node"]["opponent"] == "Joel / Nargiza"


def test_chat_export_collapses_shared_match_to_one_line():
    out = format_chat_text(_upc_shared(), {"horizon": "next", "fields": {"opponent"}})
    # The shared match must appear exactly once, attributed to the pair.
    assert out.count("Joel / Nargiza") == 1
    assert "Chau / Vu Luu" in out

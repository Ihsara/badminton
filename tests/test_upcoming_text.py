from __future__ import annotations

from badminton_tracker.upcoming_text import format_chat_text

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

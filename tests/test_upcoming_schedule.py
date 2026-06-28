from __future__ import annotations

from datetime import datetime, timedelta, timezone

from badminton_tracker.upcoming_schedule import next_refresh_delay

TZ = timezone(timedelta(hours=2))


def _state(**tour):
    base = {"start_date": "2026-03-14", "end_date": "2026-03-15",
            "status": "entries", "entries": []}
    base.update(tour)
    return {"tournaments": [base]}


def test_no_upcoming_tournament_polls_daily():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=TZ)
    assert next_refresh_delay(_state(), now) == 86400


def test_near_tournament_no_draw_polls_6h():
    now = datetime(2026, 3, 12, 12, 0, tzinfo=TZ)  # 2 days before start
    assert next_refresh_delay(_state(status="entries"), now) == 21600


def test_match_day_order_published_polls_30m():
    now = datetime(2026, 3, 14, 8, 0, tzinfo=TZ)  # on start day
    assert next_refresh_delay(_state(status="order_published"), now) == 1800


def test_friend_match_within_2h_polls_15m():
    now = datetime(2026, 3, 14, 12, 0, tzinfo=TZ)
    st = _state(status="order_published",
                entries=[{"player": "Chau", "event": "MS B",
                          "path": [{"round": "QF", "state": "scheduled",
                                    "time": "2026-03-14T13:30:00+02:00"}]}])
    assert next_refresh_delay(st, now) == 900


def test_finished_tournament_polls_daily():
    now = datetime(2026, 3, 20, 12, 0, tzinfo=TZ)  # after end_date
    assert next_refresh_delay(_state(status="order_published"), now) == 86400

"""Self-pacing refresh cadence for the upcoming pipeline + the --watch loop.

next_refresh_delay is pure (testable); watch() is the thin loop the home server
runs. The scraper polls hard only when a tracked friend's match is imminent and
backs off to daily otherwise, so it stays polite to tournamentsoftware.com.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta

DAILY = 86400
SIX_HOURS = 21600
THIRTY_MIN = 1800
FIFTEEN_MIN = 900


def _d(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def _dt(s: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


def next_refresh_delay(state: dict, now: datetime) -> int:
    today = now.date()
    best = DAILY
    for t in state.get("tournaments", []):
        start, end = _d(t.get("start_date")), _d(t.get("end_date"))
        if end and today > end:
            continue  # finished -> leave at daily
        # Imminent friend match?
        for e in t.get("entries", []):
            for node in e.get("path", []):
                if node.get("state") != "scheduled":
                    continue
                mt = _dt(node.get("time"))
                if mt and timedelta(0) <= (mt - now) <= timedelta(hours=2):
                    return FIFTEEN_MIN
        # Match day with order published?
        if (t.get("status") == "order_published" and start and end
                and start <= today <= end):
            best = min(best, THIRTY_MIN)
            continue
        # Near tournament, draw not yet published?
        if start and timedelta(0) <= (start - today) <= timedelta(days=3):
            best = min(best, SIX_HOURS)
    return best


def watch(run_once) -> None:  # pragma: no cover - thin loop
    """Repeatedly run `run_once()` (which returns the freshly-built state dict),
    then sleep until the computed next refresh."""
    while True:
        state = run_once()
        delay = next_refresh_delay(state or {}, datetime.now().astimezone())
        time.sleep(delay)

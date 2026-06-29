"""Find upcoming tournaments from the /find/tournament result DOM (pure parser
+ thin live driver). The live finder ignores explicit date params and serves a
default upcoming window with its own pagination, so the driver paginates and
de-dupes by GUID rather than trusting the query string."""

from __future__ import annotations

import re
from datetime import date, timedelta

_TOUR_RE = re.compile(
    r'<a[^>]*href="[^"]*/sport/tournament\?id=([0-9A-Fa-f-]{36})"[^>]*>(.*?)</a>',
    re.I | re.S,
)
_FI_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def _date_from_name(name: str) -> str | None:
    m = _FI_DATE_RE.search(name)
    if not m:
        return None
    d, mo, y = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def find_upcoming_tournaments(html: str, today_iso: str, horizon_days: int) -> list[dict]:
    today = date.fromisoformat(today_iso)
    horizon = today + timedelta(days=horizon_days)
    out: list[dict] = []
    seen: set[str] = set()
    for m in _TOUR_RE.finditer(html):
        guid = m.group(1)
        name = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if not name or "ilmoittautu" in name.lower() or guid.lower() in seen:
            continue
        start = _date_from_name(name)
        if start is not None:
            sd = date.fromisoformat(start)
            if sd < today or sd > horizon:
                continue
        seen.add(guid.lower())
        out.append({"name": name, "guid": guid, "start_date": start, "end_date": start})
    return out


def fetch_upcoming_tournaments(  # pragma: no cover
    page, base_url, today_iso, horizon_days, max_pages=20
):
    """Paginate the live finder window, de-dupe by GUID, return parsed list."""
    from .client import dismiss_cookies
    seen: dict[str, dict] = {}
    for pg in range(1, max_pages + 1):
        url = (f"{base_url}/find/tournament?TournamentFilter.DateFilterType=0"
               f"&page={pg}")
        page.goto(url, wait_until="domcontentloaded")
        dismiss_cookies(page)
        page.wait_for_timeout(700)  # politeness
        found = find_upcoming_tournaments(page.content(), today_iso, horizon_days)
        if not found:
            break
        before = len(seen)
        for t in found:
            seen.setdefault(t["guid"].lower(), t)
        if len(seen) == before:
            break  # no new tournaments this page
    return list(seen.values())

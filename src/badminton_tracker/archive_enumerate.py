"""Enumerate ALL tournaments from /find/tournament result pages (pure parser
+ thin live driver). Unlike the upcoming finder, no horizon filter — we archive
every tournament in the requested year range."""

from __future__ import annotations

import re

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


def parse_tournament_list(html: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for m in _TOUR_RE.finditer(html):
        guid = m.group(1)
        name = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if not name or "ilmoittautu" in name.lower() or guid.lower() in seen:
            continue
        seen.add(guid.lower())
        out.append({"id": guid, "name": name, "start_date": _date_from_name(name)})
    return out

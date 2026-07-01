"""Pure parser: a friend's /player-profile/{guid} page -> finished tournaments.

Server-rendered; no network here. The profile-header card links to player.aspx
only, so matching on tournament?id= naturally skips it. Discovery source for the
historical archive crawl (see docs/superpowers/specs/2026-07-01-archive-...).
"""

from __future__ import annotations

import re

_TOUR_RE = re.compile(
    r'<a[^>]*href="[^"]*/sport/tournament\?id=([0-9A-Fa-f-]{36})[^"]*"[^>]*>(.*?)</a>',
    re.I | re.S,
)


def parse_profile_tournaments(html: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for m in _TOUR_RE.finditer(html):
        guid = m.group(1)
        if guid.lower() in seen:
            continue
        seen.add(guid.lower())
        name = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        out.append({"id": guid, "name": name, "start_date": None})
    return out

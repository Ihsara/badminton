"""Pure parser: a friend's /player-profile/{guid} page -> finished tournaments.

Server-rendered; no network here. The profile-header card links to player.aspx
only, so matching on tournament?id= naturally skips it. Discovery source for the
historical archive crawl (see docs/superpowers/specs/2026-07-01-archive-...).
"""

from __future__ import annotations

import re

_TOUR_RE = re.compile(
    r'<a([^>]*)href="[^"]*/sport/tournament\?id=([0-9A-Fa-f-]{36})[^"]*"([^>]*)>(.*?)</a>',
    re.I | re.S,
)
_TITLE_ATTR_RE = re.compile(r'title="([^"]*)"', re.I)


def _anchor_name(pre_attrs: str, post_attrs: str, inner: str) -> str:
    """Best-effort tournament name from one <a> to a tournament.

    On the live profile DOM each tournament has TWO anchors: an image anchor
    (class="media__img") whose inner text is empty, followed by the titled name
    anchor (<h4 class="media__title"><a title="..."><span>Name</span></a>). Prefer
    the anchor's inner text; fall back to its title= attribute. The image-only
    anchor yields "" here, so the titled anchor (seen next for the same GUID) wins.
    """
    text = re.sub(r"<[^>]+>", "", inner).strip()
    if text:
        return text
    tm = _TITLE_ATTR_RE.search(pre_attrs) or _TITLE_ATTR_RE.search(post_attrs)
    return tm.group(1).strip() if tm else ""


def parse_profile_tournaments(html: str) -> list[dict]:
    # De-dup by GUID (first-seen order), but let a later anchor UPGRADE an empty
    # name — the image anchor comes first and has no text; the titled anchor next.
    order: list[str] = []
    by_guid: dict[str, dict] = {}
    for m in _TOUR_RE.finditer(html):
        guid = m.group(2)
        key = guid.lower()
        name = _anchor_name(m.group(1), m.group(3), m.group(4))
        if key not in by_guid:
            order.append(key)
            by_guid[key] = {"id": guid, "name": name, "start_date": None}
        elif name and not by_guid[key]["name"]:
            by_guid[key]["name"] = name
    return [by_guid[k] for k in order]

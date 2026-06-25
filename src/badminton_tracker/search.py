"""Resolve player display names to canonical /player-profile GUIDs via site search."""

from __future__ import annotations

import re
import urllib.parse

from playwright.sync_api import Page

from .client import dismiss_cookies
from .config import BASE_URL

_GUID_RE = re.compile(r"player-profile/([0-9a-fA-F-]{36})")


def _query(page: Page, q: str) -> list[tuple[str, str]]:
    url = f"{BASE_URL}/find/player/?q={urllib.parse.quote(q)}"
    page.goto(url, wait_until="domcontentloaded")
    dismiss_cookies(page)
    page.wait_for_timeout(900)
    found: dict[str, str] = {}
    for a in page.query_selector_all("a[href*=player-profile]"):
        href = a.get_attribute("href") or ""
        m = _GUID_RE.search(href)
        name = (a.inner_text() or "").strip()
        if m and name and name.lower() != "profiilini" and len(name) > 2:
            found.setdefault(m.group(1).lower(), name)
    return [(name, guid) for guid, name in found.items()]


def resolve_name(page: Page, name: str) -> tuple[str, str] | None:
    """Return (canonical_name, guid) for the best match, or None.

    Tries the name as given and with the word order reversed (the site indexes
    "Firstname Lastname" but some profiles register surname-first).
    """
    candidates: list[tuple[str, str]] = []
    tried: set[str] = set()
    parts = name.split()
    queries = [name]
    if len(parts) > 1:
        queries.append(" ".join(reversed(parts)))
        queries.append(parts[-1])  # surname only
    for q in queries:
        ql = q.lower()
        if ql in tried:
            continue
        tried.add(ql)
        results = _query(page, q)
        if results:
            candidates.extend(results)
            # Prefer an exact case-insensitive full-name match.
            for cname, guid in results:
                if cname.lower() == name.lower():
                    return (cname, guid)
    return candidates[0] if candidates else None

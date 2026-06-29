# src/badminton_tracker/upcoming_build.py
"""Scrape upcoming draws + order-of-play, build the public timeline JSON.

Split into a PURE assembler (assemble_upcoming — unit-tested, strips GUIDs,
applies aliases) and a thin Playwright driver (run_upcoming). Outputs:
  web/upcoming.json        — public, GUID-FREE (rule #4)
  data/upcoming_state.json — private, keeps GUIDs for re-fetch
"""

from __future__ import annotations

import json
import os
import tempfile

from . import aliases
from .config import BASE_URL, UPCOMING_JSON, UPCOMING_STATE_JSON

# Keys carrying GUIDs that must never reach the public file.
_GUID_KEYS = ("tournament_guid", "player_guid", "guid", "profile_guid")


def _strip_guids(obj):
    if isinstance(obj, dict):
        return {k: _strip_guids(v) for k, v in obj.items() if k not in _GUID_KEYS}
    if isinstance(obj, list):
        return [_strip_guids(x) for x in obj]
    return obj


def assemble_upcoming(raw: dict, alias_map: dict, now_iso: str) -> dict:
    public = _strip_guids(raw)
    for t in public.get("tournaments", []):
        for e in t.get("entries", []):
            e["player"] = aliases.apply(e["player"], alias_map)
    public["generated_at"] = now_iso
    return public


def write_outputs(public: dict, private: dict) -> None:
    _atomic_write(UPCOMING_JSON, public)
    UPCOMING_STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(UPCOMING_STATE_JSON, private)


def _atomic_write(path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(path))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _roster_for_matching():  # pragma: no cover
    import csv

    from .config import PLAYERS_CSV
    rows = []
    with open(PLAYERS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            full = (r.get("full_name") or "").strip()
            nick = (r.get("nickname") or "").strip()
            if full:  # need a full name to match on
                rows.append({"nickname": nick, "full_name": full})
    return rows


def run_upcoming(  # pragma: no cover
    tournament_guids=None, horizon_days=60, max_tournaments=20
) -> dict:
    """Tournament-first scrape: discover upcoming tournaments, match friends on each
    participant list, fetch per-friend scoped schedule pages, write public + private JSON."""
    from datetime import datetime

    from playwright.sync_api import sync_playwright

    from .client import dismiss_cookies, ensure_login, new_context
    from .exclude import load_excludes
    from .upcoming_find import fetch_upcoming_tournaments
    from .upcoming_participants import match_friends, parse_participants
    from .upcoming_schedule_parse import parse_player_schedule

    today = datetime.now().astimezone().date().isoformat()
    roster = _roster_for_matching()
    exclude = load_excludes()
    raw = {"tournaments": []}

    with sync_playwright() as p:
        browser, ctx = new_context(p)
        page = ensure_login(ctx)

        tours = fetch_upcoming_tournaments(page, BASE_URL, today, horizon_days)
        for g in (tournament_guids or []):
            if not any(t["guid"].lower() == g.lower() for t in tours):
                tours.append({"name": "", "guid": g, "start_date": None, "end_date": None})
        tours = tours[:max_tournaments]

        for t in tours:
            guid = t["guid"]
            page.goto(f"{BASE_URL}/tournament/{guid}/players", wait_until="domcontentloaded")
            dismiss_cookies(page)
            page.wait_for_timeout(900)  # politeness
            friends = match_friends(parse_participants(page.content()), roster, exclude)
            if not friends:
                continue
            entries = []
            for fr in friends:
                page.goto(f"{BASE_URL}/tournament/{guid}/player/{fr['player_no']}",
                          wait_until="domcontentloaded")
                dismiss_cookies(page)
                page.wait_for_timeout(700)
                cards = page.evaluate(
                    "() => [...document.querySelectorAll('.match')].map(n => n.innerText.trim())"
                )
                nodes = parse_player_schedule(cards, fr["full_name"])
                nodes.sort(key=lambda n: n["time"] or "")
                # group by event into separate timeline entries
                by_ev: dict[str, list] = {}
                for n in nodes:
                    by_ev.setdefault(n["event"], []).append(n)
                for ev, path in by_ev.items():
                    entries.append({"player": fr["nickname"], "player_guid": "",
                                    "event": ev, "path": path})
            if entries:
                raw["tournaments"].append({
                    "name": t["name"], "tournament_guid": guid, "venue": "",
                    "start_date": t["start_date"], "end_date": t["end_date"],
                    "status": "order_published", "entries": entries,
                })
        browser.close()

    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    public = assemble_upcoming(json.loads(json.dumps(raw)), aliases.alias_map(), now_iso)
    private = dict(raw)
    private["generated_at"] = now_iso
    write_outputs(public, private)
    return public


def _load(page, url: str) -> str:  # pragma: no cover
    from .client import dismiss_cookies
    page.goto(url, wait_until="domcontentloaded")
    dismiss_cookies(page)
    page.wait_for_timeout(900)
    return page.content()


def _resolve_event_draw(page, guid: str, event: str):  # pragma: no cover
    """Return (draws_html, draw_index|None) by matching the event label in the draws list.

    Strategy: prefer a full normalized-label match (e.g. "MS B" == "MS B") so that
    tournaments with multiple draws per discipline (MS A / MS B / MS C) pick the right
    one.  Only if no full-label match is found do we fall back to the discipline-token
    contains-match (first token of event in label) to stay resilient against minor
    label-format differences on the live site.
    """
    import re

    def _norm(s: str) -> str:
        return " ".join(s.split()).lower()

    html = _load(page, f"{BASE_URL}/sport/draws.aspx?id={guid}")
    # td.drawname links carry draw={N}; strip inner HTML tags to get the plain label.
    candidates = []
    for m in re.finditer(r'draw=(\d+)[^>]*>(.*?)</a>', html, re.S):
        idx = m.group(1)
        label = _norm(re.sub(r"<[^>]+>", " ", m.group(2)))
        candidates.append((idx, label))

    event_norm = _norm(event)
    # Pass 1: full normalized-label match (preferred — handles MS A vs MS B correctly).
    for idx, label in candidates:
        if event_norm == label:
            return html, idx

    # Pass 2: fallback — discipline-token contains-match (preserves old behaviour).
    token = event.split()[0].lower()
    for idx, label in candidates:
        if token in label:
            return html, idx

    return html, None


def _load_schedule(page, guid: str, ent: dict):  # pragma: no cover
    """Load each tournament day's Matches page, parse order-of-play rows."""
    from .upcoming_parse import parse_order_of_play
    rows = []
    for day in _day_range(ent.get("start_date"), ent.get("end_date")):
        html = _load(page, f"{BASE_URL}/tournament/{guid}/matches/{day.replace('-', '')}")
        rows.extend(parse_order_of_play(html, day))
    return rows


def _day_range(start: str | None, end: str | None):  # pragma: no cover
    from datetime import date, timedelta
    if not start:
        return []
    s = date.fromisoformat(start)
    e = date.fromisoformat(end) if end else s
    out, cur = [], s
    while cur <= e:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out

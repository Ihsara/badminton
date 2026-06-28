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


def run_upcoming() -> dict:  # pragma: no cover - exercised manually (Task 12)
    """Full scrape: confirmed friends -> upcoming entries -> draws + order-of-play
    -> per-friend paths -> write public + private JSON. Returns the public dict."""
    from datetime import datetime

    from playwright.sync_api import sync_playwright

    from .client import dismiss_cookies, ensure_login, new_context
    from .fetch import load_players
    from .upcoming_parse import find_upcoming_entries, parse_draw
    from .upcoming_path import build_path

    today = datetime.now().astimezone().date().isoformat()
    players = load_players()
    raw = {"tournaments": []}
    tour_index: dict[str, dict] = {}

    with sync_playwright() as p:
        browser, ctx = new_context(p)
        page = ensure_login(ctx)
        for pl in players:
            page.goto(f"{BASE_URL}/player-profile/{pl['guid']}/tournaments",
                      wait_until="domcontentloaded")
            dismiss_cookies(page)
            page.wait_for_timeout(1200)
            entries = find_upcoming_entries(page.content(), today)
            for ent in entries:
                guid = ent["tournament_guid"]
                if not guid:
                    continue
                t = tour_index.get(guid)
                if t is None:
                    # Schedule (order-of-play) is per tournament — load it once.
                    schedule = _load_schedule(page, guid, ent)
                    status = "order_published" if schedule else "draw_published"
                    t = {"name": ent["tournament"], "tournament_guid": guid,
                         "venue": "", "start_date": ent["start_date"],
                         "end_date": ent["end_date"], "status": status,
                         "entries": [], "_schedule": schedule}
                    tour_index[guid] = t
                    raw["tournaments"].append(t)
                # Each event has its OWN draw, so resolve per event. Prefer the
                # draw index the profile card already carries (ent["draw_index"]);
                # fall back to matching the draws list only when it's absent.
                draw_index = ent.get("draw_index")
                if not draw_index:
                    _draws_html, draw_index = _resolve_event_draw(page, guid, ent["event"])
                if draw_index:
                    draw_url = f"{BASE_URL}/tournament/{guid}/draw/{draw_index}"
                    draw_rounds = parse_draw(_load(page, draw_url))
                else:
                    draw_rounds = []
                path = build_path(draw_rounds, t["_schedule"],
                                  pl["nickname"] or pl["full_name"], ent["event"], today)
                t["entries"].append({"player": pl["nickname"] or pl["full_name"],
                                     "player_guid": pl["guid"], "event": ent["event"],
                                     "path": path})
            page.wait_for_timeout(800)  # politeness
        browser.close()

    for t in raw["tournaments"]:
        t.pop("_schedule", None)

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

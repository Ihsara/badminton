"""Pure HTML parsers for the upcoming-tournament pipeline.

No network: every function takes raw HTML and returns plain dicts/lists, so they
are unit-tested against saved fixtures. Mirrors the extraction style of parse.py
but uses the stdlib HTMLParser instead of Playwright page.evaluate, since these
run in the build step over already-fetched HTML.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser


class _DrawParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rounds: list[dict] = []
        self._cur: dict | None = None
        self._capture: str | None = None  # 'title' | 'value'
        self._buf: list[str] = []
        self._depth = 0  # nesting depth within the active capture element

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        cls = (a.get("class") or "")
        if self._capture:
            # Already capturing: any nested inner tag deepens the element so we
            # don't flush early on its close-tag.
            self._depth += 1
        elif "bracket-round__title" in cls:
            self._capture, self._buf, self._depth = "title", [], 1
        elif "nav-link__value" in cls and self._cur is not None:
            self._capture, self._buf, self._depth = "value", [], 1
        elif tag == "time" and self._cur is not None:
            dt = a.get("datetime")
            if dt and self._cur.get("scheduled_iso") is None:
                self._cur["scheduled_iso"] = dt

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._capture:
            return
        self._depth -= 1
        if self._depth > 0:
            return  # still inside a nested inner tag; not the capturing element
        if self._capture == "title":
            label = "".join(self._buf).strip()
            self._cur = {"round_label": label, "slots": [], "scheduled_iso": None}
            self.rounds.append(self._cur)
        elif self._capture == "value" and self._cur is not None:
            val = "".join(self._buf).strip()
            if val:
                # Only the displayed match-group is captured, so slots is 0-2.
                self._cur["slots"].append(val)
        self._capture = None


def parse_draw(html: str) -> list[dict]:
    p = _DrawParser()
    p.feed(html)
    return p.rounds


_COURT_RE = re.compile(r"(K\d+|Court\s*\d+)", re.IGNORECASE)
# Known event codes appear at the head of the match title ("MS B Quarter final").
_EVENT_HEAD_RE = re.compile(
    r"^((?:MS|WS|MD|WD|XD|MK|NK|MN|NN|SN)\b(?:\s+\S+)?)\s+(.*)$"
)


def _court_from_title(title: str | None) -> str | None:
    if not title:
        return None
    m = _COURT_RE.search(title)
    return m.group(1).replace("Court ", "K").replace("Court", "K") if m else None


def _split_title(text: str) -> tuple[str, str]:
    """'MS B Quarter final' -> ('MS B', 'Quarter final')."""
    m = _EVENT_HEAD_RE.match(text.strip())
    return (m.group(1).strip(), m.group(2).strip()) if m else ("", text.strip())


class _OrderParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict] = []
        self._time: str | None = None
        self._cur: dict | None = None
        self._capture: str | None = None  # 'time' | 'title' | 'value'
        self._buf: list[str] = []
        self._depth = 0  # nesting depth within the active capture element

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        cls = a.get("class") or ""
        if self._capture:
            # Already capturing: any nested inner tag deepens the element so we
            # don't flush early on its close-tag.
            self._depth += 1
        elif "match-group__header" in cls:
            self._capture, self._buf, self._depth = "time", [], 1
        elif "match--list" in cls:
            self._cur = {
                "time": self._time,
                "court": None,
                "event": "",
                "round_label": "",
                "players": [],
            }
            self.rows.append(self._cur)
        elif "match__header-title" in cls and self._cur is not None:
            self._capture, self._buf, self._depth = "title", [], 1
        elif "match__header-aside" in cls and self._cur is not None:
            self._cur["court"] = _court_from_title(a.get("title"))
            # match__header-aside sets state via attribute; if a capture is
            # active, we just increment depth like any other nested tag.
            if self._capture:
                self._depth += 1
        elif "nav-link__value" in cls and self._cur is not None:
            self._capture, self._buf, self._depth = "value", [], 1

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._capture:
            return
        self._depth -= 1
        if self._depth > 0:
            return  # still inside a nested inner tag; not the capturing element
        text = "".join(self._buf).strip()
        if self._capture == "time":
            self._time = text
        elif self._capture == "title" and self._cur is not None:
            self._cur["event"], self._cur["round_label"] = _split_title(text)
        elif self._capture == "value" and self._cur is not None and text:
            self._cur["players"].append(text)
        self._capture = None


def parse_order_of_play(html: str, date_iso: str) -> list[dict]:
    p = _OrderParser()
    p.feed(html)
    for r in p.rows:
        r["date"] = date_iso
    return p.rows


# GUID appears as a query-string id on the live site (?id=GUID in
# /sport/tournament, /sport/draw.aspx, ...) and as a path segment on the older
# /tournament/GUID shape; accept both.
_GUID = r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
_GUID_RE = re.compile(r"[/=](" + _GUID + r")")
# Live <time datetime="YYYY-MM-DD HH.MM"> — only the date part is needed.
_ISO_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_DRAW_IDX_RE = re.compile(r"[?&]draw=(\d+)")
# Fallback: Finnish d.m.yyyy footer text (older hand-authored fixture shape).
_DATE_RANGE_RE = re.compile(
    r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s*-\s*(\d{1,2})\.(\d{1,2})\.(\d{4})"
)
_SINGLE_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def _iso(d: str, m: str, y: str) -> str:
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def _parse_dates(footer: str) -> tuple[str | None, str | None]:
    """Fallback date parse from Finnish d.m.yyyy footer text."""
    m = _DATE_RANGE_RE.search(footer)
    if m:
        return _iso(m.group(1), m.group(2), m.group(3)), _iso(m.group(4), m.group(5), m.group(6))
    s = _SINGLE_DATE_RE.search(footer)
    if s:
        iso = _iso(s.group(1), s.group(2), s.group(3))
        return iso, iso
    return None, None


class _EntriesParser(HTMLParser):
    """Collect tournament cards from a profile /tournaments page.

    One card = one tournament with possibly several events (Luokka:). For each
    card we gather the name, GUID, the <time> dates, and a (event, draw_index)
    list — then emit one entry per event. The live DOM puts dates in <time> tags
    and the GUID in ?id=...; an older hand-authored fixture used a .module__footer
    text date-range and /tournament/GUID, so both paths are supported.
    """

    def __init__(self) -> None:
        super().__init__()
        self.cards: list[dict] = []
        self._cur: dict | None = None
        self._capture: str | None = None  # 'title' | 'footer' | 'divider'
        self._buf: list[str] = []
        self._depth = 0  # nesting depth within the active capture element

    def _new_card(self) -> None:
        self._cur = {
            "tournament": "", "tournament_guid": None,
            "dates": [],          # ISO date strings from <time> tags (live)
            "footer": None,       # raw footer text (fallback)
            "events": [],         # list of [event_label, draw_index|None]
            "_pending_event": None,
        }
        self.cards.append(self._cur)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        cls = a.get("class") or ""
        if "module--card" in cls:
            # A new card may begin while a previous capture was left dangling
            # (defensive): reset capture state.
            self._capture, self._depth = None, 0
            self._new_card()
            return
        if self._cur is None:
            return

        href = a.get("href") or ""
        # Href/attr-based extraction runs REGARDLESS of capture state, because the
        # draw link <a> is nested INSIDE the capturing module-divider__body span.
        if tag == "time":
            d = _ISO_DATE_RE.search(a.get("datetime") or "")
            if d:
                self._cur["dates"].append(d.group(1))
        elif href:
            g = _GUID_RE.search(href)
            if g and not self._cur["tournament_guid"]:
                self._cur["tournament_guid"] = g.group(1)
            if "draw.aspx" in href or "/draw/" in href:
                m = _DRAW_IDX_RE.search(href)
                if m and self._cur["_pending_event"] is not None:
                    self._cur["events"].append([self._cur["_pending_event"], m.group(1)])
                    self._cur["_pending_event"] = None

        if self._capture:
            self._depth += 1  # nested inner tag — don't flush the text early
            return

        # Start a text capture for the title / footer / luokka label.
        if "media__title" in cls or "media__link" in cls:
            self._capture, self._buf, self._depth = "title", [], 1
        elif "module__footer" in cls:
            self._capture, self._buf, self._depth = "footer", [], 1
        elif "module-divider__body" in cls or tag == "h4":
            # Live: the luokka label sits in a module-divider__body span.
            # Fallback fixture: a bare <h4>Luokka: X</h4>.
            self._capture, self._buf, self._depth = "divider", [], 1

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._capture or self._cur is None:
            return
        self._depth -= 1
        if self._depth > 0:
            return  # still inside a nested inner tag
        text = "".join(self._buf).strip()
        if self._capture == "title" and not self._cur["tournament"]:
            self._cur["tournament"] = text
        elif self._capture == "footer":
            self._cur["footer"] = text
        elif self._capture == "divider" and text.lower().startswith("luokka"):
            # A new luokka label. Flush any previous label that never got a draw
            # link (e.g. a recreational class) as an event with draw_index None.
            if self._cur["_pending_event"] is not None:
                self._cur["events"].append([self._cur["_pending_event"], None])
            self._cur["_pending_event"] = text.split(":", 1)[-1].strip()
        self._capture = None


def _card_dates(card: dict) -> tuple[str | None, str | None]:
    dates = card["dates"]
    if dates:
        return dates[0], (dates[1] if len(dates) > 1 else dates[0])
    if card["footer"]:
        return _parse_dates(card["footer"])
    return None, None


def find_upcoming_entries(html: str, today_iso: str) -> list[dict]:
    p = _EntriesParser()
    p.feed(html)
    out: list[dict] = []
    for c in p.cards:
        # Flush a trailing luokka with no draw link (one-event-no-draw cards).
        if c["_pending_event"] is not None:
            c["events"].append([c["_pending_event"], None])
        # Fallback: an older fixture has a luokka but no draw link and the label
        # was captured via the same divider path — already handled above. If a
        # card has a footer/guid but no events were detected via dividers, skip it.
        start, end = _card_dates(c)
        if end is not None and end < today_iso:
            continue  # whole tournament is in the past
        for event, draw_index in c["events"]:
            out.append({
                "tournament": c["tournament"],
                "tournament_guid": c["tournament_guid"],
                "event": event,
                "start_date": start,
                "end_date": end,
                "draw_index": draw_index,
            })
    return out

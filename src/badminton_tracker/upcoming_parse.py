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

"""Pure HTML parsers for the upcoming-tournament pipeline.

No network: every function takes raw HTML and returns plain dicts/lists, so they
are unit-tested against saved fixtures. Mirrors the extraction style of parse.py
but uses the stdlib HTMLParser instead of Playwright page.evaluate, since these
run in the build step over already-fetched HTML.
"""

from __future__ import annotations

from html.parser import HTMLParser


class _DrawParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rounds: list[dict] = []
        self._cur: dict | None = None
        self._capture: str | None = None  # 'title' | 'value' | 'time'
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        cls = (a.get("class") or "")
        if "bracket-round__title" in cls:
            self._capture, self._buf = "title", []
        elif "nav-link__value" in cls and self._cur is not None:
            self._capture, self._buf = "value", []
        elif tag == "time" and self._cur is not None:
            dt = a.get("datetime")
            if dt and self._cur.get("scheduled_iso") is None:
                self._cur["scheduled_iso"] = dt

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture == "title":
            label = "".join(self._buf).strip()
            self._cur = {"round_label": label, "slots": [], "scheduled_iso": None}
            self.rounds.append(self._cur)
        elif self._capture == "value" and self._cur is not None:
            val = "".join(self._buf).strip()
            if val:
                self._cur["slots"].append(val)
        if self._capture in ("title", "value"):
            self._capture = None


def parse_draw(html: str) -> list[dict]:
    p = _DrawParser()
    p.feed(html)
    return p.rounds

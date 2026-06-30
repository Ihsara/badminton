"""Pure HTML->dict parsers for tournament draw lists and full brackets.

No network. Unit-tested against saved fixtures. Uses the same depth-tracked
HTMLParser style as upcoming_parse._DrawParser for robustness against nested tags.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# Draw list
# ---------------------------------------------------------------------------

_DRAW_LINK_RE = re.compile(
    r'<a[^>]*href="([^"]*draw[^"]*)"[^>]*>(.*?)</a>', re.I | re.S
)


def parse_draw_list(html: str) -> list[dict]:
    """Return one dict per draw link found in the HTML.

    Each dict: {"id": href_str, "name": str, "draw_type": "unknown", "ordering": int}
    De-duped by href; ordering = order of first appearance.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for i, m in enumerate(_DRAW_LINK_RE.finditer(html)):
        href = m.group(1)
        name = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if not name or href in seen:
            continue
        seen.add(href)
        out.append({"id": href, "name": name, "draw_type": "unknown", "ordering": i})
    return out


# ---------------------------------------------------------------------------
# Bracket
# ---------------------------------------------------------------------------

# Round labels in finals-first order; round_index = position in this list when
# matched, else a large fallback so unknown rounds sort as "earliest".
_ROUND_ORDER = ["final", "semi", "quarter", "r16", "r32", "r64", "round of"]


def _round_index(label: str) -> int:
    low = label.lower()
    for i, key in enumerate(_ROUND_ORDER):
        if key in low:
            return i
    return 99


class _BracketParser(HTMLParser):
    """Single-pass depth-tracked parser for knockout bracket HTML.

    Mirrors the structure of upcoming_parse._DrawParser:
    - _capture tracks what text we are currently accumulating ('title' | 'player').
    - _depth counts how deep inside the capturing element we are, so nested tags
      do not flush the buffer early.
    - match containers (bracket-round__match-group) and player rows (match__row)
      are tracked with flags/stacks rather than nesting depth, since the match-group
      can contain multiple rows.
    """

    def __init__(self) -> None:
        super().__init__()
        self.matches: list[dict] = []
        # Current round state
        self._round_label: str | None = None
        self._round_position = 0
        # Current match-group state
        self._in_match = False
        self._cur: dict | None = None
        self._match_depth = 0  # depth inside bracket-round__match-group tag
        # Current player-row state
        self._in_row = False
        self._row_winner = False
        self._row_depth = 0  # depth inside match__row tag
        self._cur_side: list[dict] | None = None
        # Generic text capture ('title' | 'player')
        self._capture: str | None = None
        self._buf: list[str] = []
        self._cap_depth = 0  # depth inside capturing element

    # ------------------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        cls = a.get("class") or ""

        # Depth tracking for active text capture
        if self._capture:
            self._cap_depth += 1
            # time element inside a match group
            if tag == "time" and self._cur is not None:
                dt = a.get("datetime")
                if dt and self._cur["scheduled_iso"] is None:
                    self._cur["scheduled_iso"] = dt
            return

        if "bracket-round__title" in cls:
            self._capture, self._buf, self._cap_depth = "title", [], 1
            return

        if "bracket-round__match-group" in cls and "wrapper" not in cls:
            self._commit_match()  # commit any previous open match
            self._in_match = True
            self._match_depth = 1
            self._cur = {
                "round_label": self._round_label or "",
                "round_index": _round_index(self._round_label or ""),
                "position": self._round_position,
                "sides": [],
                # score markup unconfirmed against a real played bracket;
                # defaults to None until a real fixture is captured (see plan T5 addendum).
                "score_raw": None,
                "winner_side": None,
                "scheduled_iso": None,
                "court": None,
            }
            self._round_position += 1
            return

        if self._in_match:
            self._match_depth += 1

            if "match__row" in cls:
                self._in_row = True
                self._row_depth = 1
                self._row_winner = "has-won" in cls
                self._cur_side = []
                return

            if self._in_row:
                if "nav-link__value" in cls:
                    # Start a text capture; row_depth is NOT incremented here
                    # because the capture manages its own depth via _cap_depth.
                    self._capture, self._buf, self._cap_depth = "player", [], 1
                    return
                # Track nesting for all other tags inside the row
                self._row_depth += 1

            if tag == "time" and self._cur is not None:
                dt = a.get("datetime")
                if dt and self._cur["scheduled_iso"] is None:
                    self._cur["scheduled_iso"] = dt

    # ------------------------------------------------------------------
    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)

    # ------------------------------------------------------------------
    def handle_endtag(self, tag: str) -> None:
        # Text capture flush (depth-tracked, same pattern as _DrawParser)
        if self._capture:
            self._cap_depth -= 1
            if self._cap_depth > 0:
                return
            text = "".join(self._buf).strip()
            if self._capture == "title":
                self._commit_match()
                self._round_label = text
                self._round_position = 0
            elif self._capture == "player" and self._cur_side is not None:
                if text:
                    self._cur_side.append(
                        {"name": text, "profile_guid": None, "seed": None}
                    )
            self._capture = None
            return

        if self._in_row:
            self._row_depth -= 1
            if self._row_depth <= 0:
                # Closing the match__row div: commit the side
                if self._cur_side is not None and self._cur is not None:
                    self._cur["sides"].append(self._cur_side)
                    if self._row_winner:
                        self._cur["winner_side"] = len(self._cur["sides"])
                self._cur_side = None
                self._in_row = False
                self._row_winner = False
            return

        if self._in_match:
            self._match_depth -= 1
            if self._match_depth <= 0:
                self._commit_match()
                self._in_match = False

    # ------------------------------------------------------------------
    def _commit_match(self) -> None:
        """Flush the current match dict to self.matches if it has any sides."""
        if self._cur is not None and self._cur["sides"]:
            self.matches.append(self._cur)
        self._cur = None

    def finalize(self) -> None:
        """Call after feed() to flush any trailing open match."""
        self._commit_match()


def parse_bracket(html: str) -> list[dict]:
    """Parse a knockout draw page and return one dict per match-group."""
    p = _BracketParser()
    p.feed(html)
    p.finalize()
    return p.matches

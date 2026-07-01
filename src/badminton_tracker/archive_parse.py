"""Pure HTML->dict parsers for tournament draw lists and full brackets.

No network. Unit-tested against saved fixtures. Uses the same depth-tracked
HTMLParser style as upcoming_parse._DrawParser for robustness against nested tags.
"""

from __future__ import annotations

import re

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

_ROUND_OF_N = {16: 3, 32: 4, 64: 5}
_ROUND_OF_RE = re.compile(r"round\s+of\s*(\d+)", re.I)
_R_SHORT_RE = re.compile(r"^r(\d+)$", re.I)


def _round_index(label: str) -> int:
    """Return a finals-first index for a round label (0=Final, higher=earlier round).

    Canonical mappings:
      Final               -> 0
      Semi final / Semi-final / Semifinal -> 1
      Quarter final / Quarter-final / Quarterfinal -> 2
      Round of 16 / R16   -> 3
      Round of 32 / R32   -> 4
      Round of 64 / R64   -> 5
      unknown             -> 99
    """
    low = label.strip().lower()

    # More-specific checks before bare "final" to avoid substring false-matches.
    if "semi" in low:
        return 1
    if "quarter" in low:
        return 2

    # "Round of N" long form
    m = _ROUND_OF_RE.search(low)
    if m:
        return _ROUND_OF_N.get(int(m.group(1)), 99)

    # Short form: R16 / R32 / R64
    m2 = _R_SHORT_RE.match(low)
    if m2:
        return _ROUND_OF_N.get(int(m2.group(1)), 99)

    if "final" in low:
        return 0

    return 99


_DRAW_HREF_RE = re.compile(r"draw\.aspx\?id=([0-9A-Fa-f-]{36})&(?:amp;)?draw=(\d+)", re.I)
_PLAYER_HREF_RE = re.compile(r"player\.aspx\?id=([0-9A-Fa-f-]{36})&(?:amp;)?player=(\d+)", re.I)
_NAME_RE = re.compile(r'nav-link__value">(.*?)</span>', re.S)
_SEED_RE = re.compile(r"\[(\d+)")
_MATCH_ITEM_RE = re.compile(
    r'<div class="match match--list">(.*?)(?=<div class="match match--list">|</ol>|$)', re.S
)
_MATCH_ROW_RE = re.compile(
    r'<div class="match__row( has-won)?\s*">(.*?)'
    r'(?=<div class="match__row(?: has-won)?\s*">|<div class="match__result"|$)',
    re.S,
)


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def parse_matches_page(html: str) -> list[dict]:
    """Parse a tournament-scoped /sport/matches.aspx page into per-match dicts.

    Each match self-describes its draw + round via match__header-title; winner is
    the match__row carrying has-won; score is per-game points cells (side1 first).
    """
    out: list[dict] = []
    positions: dict[tuple[str, str], int] = {}
    for block_m in _MATCH_ITEM_RE.finditer(html):
        block = block_m.group(0)
        header, _, rest = block.partition('class="match__body"')

        dm = _DRAW_HREF_RE.search(header)
        if not dm:
            continue
        draw_id = f"{dm.group(1)}:{dm.group(2)}"
        # draw name = first nav-link__value inside the header
        hn = _NAME_RE.search(header)
        draw_name = _clean(hn.group(1)) if hn else ""
        # round label = title="..." on the 2nd header-title-item
        titles = re.findall(r'title="([^"]+)"', header)
        round_label = titles[0] if titles else ""

        sides: list[list[dict]] = []
        winner_side: int | None = None
        for rm in _MATCH_ROW_RE.finditer(rest):
            is_win = bool(rm.group(1))
            row = rm.group(2)
            entrants: list[dict] = []
            for pm in _PLAYER_HREF_RE.finditer(row):
                guid, player_no = pm.group(1), pm.group(2)
                # the name span follows this anchor
                after = row[pm.end():]
                nm = _NAME_RE.search(after)
                raw_name = _clean(nm.group(1)) if nm else ""
                seed_m = _SEED_RE.search(raw_name)
                name = re.sub(r"\s*\[.*?\]\s*$", "", raw_name).strip()
                entrants.append({
                    "name": name,
                    "profile_guid": f"{guid}:{player_no}",
                    "seed": int(seed_m.group(1)) if seed_m else None,
                })
            if not entrants:
                continue
            sides.append(entrants)
            if is_win:
                winner_side = len(sides)

        if not sides:
            continue

        # score: one <ul class="points"> per game; two cells (side1, side2)
        games: list[str] = []
        result_seg = rest.partition('class="match__result"')[2]
        for ul in re.finditer(r'<ul class="points">(.*?)</ul>', result_seg, re.S):
            cells = re.findall(r'points__cell[^>]*>\s*([0-9]+)\s*<', ul.group(1))
            if len(cells) >= 2:
                games.append(f"{cells[0]}-{cells[1]}")
        score_raw = " ".join(games) if games else None

        key = (draw_id, round_label)
        pos = positions.get(key, 0)
        positions[key] = pos + 1
        out.append({
            "draw_id": draw_id,
            "draw_name": draw_name,
            "round_label": round_label,
            "round_index": _round_index(round_label),
            "position": pos,
            "sides": sides,
            "winner_side": winner_side,
            "score_raw": score_raw,
            "scheduled_iso": None,
        })
    return out

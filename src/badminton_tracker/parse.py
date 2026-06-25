"""Extract match rows from a player-profile /tournaments page."""

from __future__ import annotations

from playwright.sync_api import Page

# Finnish event-class codes -> the English codes used in the source workbook.
CATEGORY_MAP = {
    "MK": "MS",  # Miesten kaksinpeli
    "NK": "WS",  # Naisten kaksinpeli
    "MN": "MD",  # Miesten nelinpeli
    "NN": "WD",  # Naisten nelinpeli
    "SN": "XD",  # Sekanelinpeli
    "MS": "MS",
    "WS": "WS",
    "MD": "MD",
    "WD": "WD",
    "XD": "XD",
}

# JS walks each tournament card, tracking the current "Luokka:" category header,
# and emits structured data for every match in DOM order.
_EXTRACT_JS = r"""
() => {
  const text = (el) => (el ? el.innerText.trim() : null);

  const extractMatch = (node, category) => {
    const rows = [...node.querySelectorAll('.match__body .match__row')].map((row) => ({
      players: [...row.querySelectorAll('.match__row-title-value .nav-link__value')]
        .map((v) => v.innerText.trim())
        .filter(Boolean),
      hasWon: row.classList.contains('has-won'),
    }));
    const sets = [...node.querySelectorAll('.match__result ul.points')].map((ul) =>
      [...ul.querySelectorAll('.points__cell')].map((c) => c.innerText.trim())
    );
    const footer = [...node.querySelectorAll('.match__footer-list-item .nav-link__value')]
      .map((v) => v.innerText.trim());
    return {
      category,
      round: text(node.querySelector('.match__header-title')),
      duration: text(node.querySelector('.match__header-aside time')),
      status: text(node.querySelector('.match__status')),
      rows,
      sets,
      date: footer[0] || null,
      location: footer[1] || null,
    };
  };

  const out = [];
  for (const card of document.querySelectorAll('.module--card')) {
    let tournament = text(card.querySelector('.media__title'));
    if (!tournament) {
      for (const h of card.querySelectorAll('h4')) {
        if (!h.innerText.trim().toLowerCase().startsWith('luokka')) {
          tournament = h.innerText.trim();
          break;
        }
      }
    }
    const matches = [];
    let category = null;
    const walker = document.createTreeWalker(card, NodeFilter.SHOW_ELEMENT);
    let node = walker.currentNode;
    while (node) {
      if (node.tagName === 'H4') {
        const t = node.innerText.trim();
        if (t.toLowerCase().startsWith('luokka')) {
          category = t.replace(/^luokka:\s*/i, '').trim();
        }
      } else if (node.classList && node.classList.contains('match')) {
        matches.push(extractMatch(node, category));
      }
      node = walker.nextNode();
    }
    if (matches.length) out.push({ tournament, matches });
  }
  return out;
}
"""


def _norm_tokens(name: str) -> set[str]:
    return {t for t in name.lower().replace(".", " ").split() if t}


def _split_category(raw: str | None) -> tuple[str, str]:
    """'MD C' -> ('MD', 'C'); 'MN-rento' -> ('MD', 'rento')."""
    if not raw:
        return ("", "")
    head, _, tail = raw.partition(" ")
    code, _, lvl = head.partition("-")
    level = (lvl + (" " + tail if tail else "")).strip() or tail.strip()
    return (CATEGORY_MAP.get(code.upper(), code), level)


def extract_player_matches(page: Page, player_name: str) -> list[dict]:
    """Return normalised match rows for the profile currently loaded on `page`."""
    cards = page.evaluate(_EXTRACT_JS)
    own_tokens = _norm_tokens(player_name)
    rows: list[dict] = []
    for card in cards:
        tournament = card["tournament"]
        for m in card["matches"]:
            teams = m["rows"]
            if len(teams) < 2:
                continue
            # Identify which team row is the profile owner's; default to the top row.
            own_idx = 0
            for i, team in enumerate(teams):
                joined = _norm_tokens(" ".join(team["players"]))
                if own_tokens & joined:
                    own_idx = i
                    break
            opp_idx = 1 - own_idx if len(teams) == 2 else (0 if own_idx else 1)
            own, opp = teams[own_idx], teams[opp_idx]

            # Each set ul holds [topRowScore, bottomRowScore]; pick by row index.
            own_scores, opp_scores = [], []
            for s in m["sets"]:
                if len(s) >= 2:
                    own_scores.append(_to_int(s[own_idx]))
                    opp_scores.append(_to_int(s[opp_idx]))

            status = (m["status"] or "").upper()
            if status == "V":
                result = "WIN"
            elif status == "H":
                result = "LOSS"
            else:
                result = "WIN" if own["hasWon"] else "LOSS"

            category, level = _split_category(m["category"])
            rows.append(
                {
                    "date": m["date"],
                    "tournament": tournament,
                    "category": category,
                    "level": level,
                    "round": m["round"],
                    "player_1": own["players"][0] if own["players"] else "",
                    "player_2": own["players"][1] if len(own["players"]) > 1 else "",
                    "opponent_1": opp["players"][0] if opp["players"] else "",
                    "opponent_2": opp["players"][1] if len(opp["players"]) > 1 else "",
                    "result": result,
                    "set_1_own": own_scores[0] if len(own_scores) > 0 else None,
                    "set_1_opp": opp_scores[0] if len(opp_scores) > 0 else None,
                    "set_2_own": own_scores[1] if len(own_scores) > 1 else None,
                    "set_2_opp": opp_scores[1] if len(opp_scores) > 1 else None,
                    "set_3_own": own_scores[2] if len(own_scores) > 2 else None,
                    "set_3_opp": opp_scores[2] if len(opp_scores) > 2 else None,
                    "duration": m["duration"],
                    "location": m["location"],
                }
            )
    return rows


def _to_int(s: str) -> int | None:
    try:
        return int(s.strip())
    except (ValueError, AttributeError):
        return None

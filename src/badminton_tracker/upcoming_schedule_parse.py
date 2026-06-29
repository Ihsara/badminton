"""Pure parser for a tournament-scoped player page's .match cards (text form).

The live driver extracts each .match node's innerText and hands the list here.
A card lists the two teams (the friend's team and the opponents) between the
2-line header and an 'H2H' marker, then a Finnish 'd.m.yyyy HH.MM' line and the
court. Round-robin pool matches are all 'scheduled'."""

from __future__ import annotations

import re

_FI_DT_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2})\.(\d{2})")
_SEED_RE = re.compile(r"\s*\[\d+\]\s*$")
# Helsinki summer time (EEST); the tournaments are Finnish so times are local +03.
_TZ_OFFSET = "+03:00"
# A real court designator carries a digit (K2, A1, Court 5, Field 3). A bare
# multi-letter word with no digit is the venue name (e.g. "Talihalli"), not a court.
_COURT_RE = re.compile(r"\d")


def _tokens(name: str) -> set[str]:
    return {t for t in re.sub(r"[.,]", " ", name).lower().split() if t}


def _strip_seed(n: str) -> str:
    return _SEED_RE.sub("", n).strip()


def _norm_round(label: str) -> str:
    s = label.strip().lower()
    if s.startswith("round"):
        m = re.search(r"\d+", s)
        return f"R{m.group()}" if m else label.strip()
    return {"final": "Final"}.get(s, label.strip())


def _iso_time(card: str) -> str | None:
    m = _FI_DT_RE.search(card)
    if not m:
        return None
    d, mo, y, hh, mm = m.groups()
    return (
        f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        f"T{int(hh):02d}:{int(mm):02d}:00{_TZ_OFFSET}"
    )


def parse_player_schedule(cards: list[str], friend_full_name: str) -> list[dict]:
    own = _tokens(friend_full_name)
    out: list[dict] = []
    for card in cards:
        lines = [ln.strip() for ln in card.splitlines() if ln.strip()]
        if len(lines) < 4:
            continue
        round_label, event = lines[0], lines[1]

        # Collect player names from lines[2:] until H2H
        names: list[str] = []
        for ln in lines[2:]:
            if ln.upper() == "H2H":
                break
            names.append(ln)

        # Court = the final line of the card if it isn't a date/time line AND
        # it looks like a real court designator (carries a digit, e.g. K2 / Court 5).
        # The live pool-match cards put the venue name ("Talihalli") here instead,
        # which is not a court — drop it so the UI doesn't render "Court Talihalli".
        court = None
        last = lines[-1]
        if not _FI_DT_RE.search(last) and _COURT_RE.search(last):
            court = last

        names = [_strip_seed(n) for n in names]

        # Split into own team / opponents by which side holds the friend
        if len(names) == 4:
            t1, t2 = names[:2], names[2:]
        elif len(names) == 2:
            t1, t2 = [names[0]], [names[1]]
        else:
            t1, t2 = names, []
        own_team, opp_team = (t1, t2)
        if _tokens(" ".join(t2)) & own:
            own_team, opp_team = t2, t1

        partner = next((n for n in own_team if not (_tokens(n) & own)), None)
        opponent = " / ".join(opp_team) or None
        out.append({
            "round": _norm_round(round_label), "event": event,
            "partner": partner, "opponent": opponent, "court": court,
            "time": _iso_time(card), "time_kind": "exact", "state": "scheduled",
        })
    return out

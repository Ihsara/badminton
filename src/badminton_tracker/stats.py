"""Compute player/tournament aggregates in Python (replacing the Excel formulas).

The source workbook derived its "Individual statistics" and "Insights" sheets from
spreadsheet FILTER/COUNT formulas. Per the project rules these are recomputed here
in Python and written out as plain values.
"""

from __future__ import annotations

from collections import defaultdict

from .parse import _norm_tokens


def _sets(m: dict) -> list[tuple[int, int]]:
    out = []
    for own, opp in (
        (m["set_1_own"], m["set_1_opp"]),
        (m["set_2_own"], m["set_2_opp"]),
        (m["set_3_own"], m["set_3_opp"]),
    ):
        if isinstance(own, int) and isinstance(opp, int):
            out.append((own, opp))
    return out


def _perspective(m: dict, friend_tokens: set[str]) -> dict | None:
    """Return the match seen from `friend`'s side, or None if they didn't play.

    Player 1/2 are the "own" side as scraped; if the friend is on the opponent
    side, win/loss and scores are flipped so stats read from their perspective.
    """
    own_side = friend_tokens & (_norm_tokens(m["player_1"]) | _norm_tokens(m["player_2"]))
    opp_side = friend_tokens & (_norm_tokens(m["opponent_1"]) | _norm_tokens(m["opponent_2"]))
    if own_side:
        sets = _sets(m)
        won = m["result"] == "WIN"
    elif opp_side:
        sets = [(o, s) for s, o in _sets(m)]
        won = m["result"] == "LOSS"
    else:
        return None
    return {"won": won, "sets": sets}


def _blank_stat() -> dict:
    return {
        "games": 0,
        "wins": 0,
        "losses": 0,
        "sets_won": 0,
        "sets_lost": 0,
        "points_for": 0,
        "points_against": 0,
        "third_set_games": 0,
    }


def _accumulate(stat: dict, view: dict) -> None:
    stat["games"] += 1
    stat["wins"] += 1 if view["won"] else 0
    stat["losses"] += 0 if view["won"] else 1
    if len(view["sets"]) >= 3:
        stat["third_set_games"] += 1
    for own, opp in view["sets"]:
        stat["points_for"] += own
        stat["points_against"] += opp
        if own > opp:
            stat["sets_won"] += 1
        else:
            stat["sets_lost"] += 1


def _finalise(stat: dict) -> dict:
    games = stat["games"]
    sets = stat["sets_won"] + stat["sets_lost"]
    stat["win_ratio"] = round(stat["wins"] / games, 3) if games else None
    stat["points_per_set"] = round(stat["points_for"] / sets, 2) if sets else None
    stat["third_set_ratio"] = round(stat["third_set_games"] / games, 3) if games else None
    return stat


def player_stats(matches: list[dict], roster: list[dict]) -> list[dict]:
    """Overall per-friend statistics across all fetched matches."""
    out = []
    for friend in roster:
        label = friend["nickname"] or friend["full_name"]
        tokens = _norm_tokens(friend["full_name"]) or _norm_tokens(friend["nickname"])
        stat = _blank_stat()
        for m in matches:
            view = _perspective(m, tokens)
            if view:
                _accumulate(stat, view)
        if stat["games"]:
            out.append({"player": label, **_finalise(stat)})
    out.sort(key=lambda r: (-r["wins"], -r["games"]))
    return out


def tournament_stats(matches: list[dict], roster: list[dict]) -> list[dict]:
    """Per-friend, per-tournament statistics."""
    grouped: dict[tuple[str, str], dict] = defaultdict(_blank_stat)
    for friend in roster:
        label = friend["nickname"] or friend["full_name"]
        tokens = _norm_tokens(friend["full_name"]) or _norm_tokens(friend["nickname"])
        for m in matches:
            view = _perspective(m, tokens)
            if view:
                _accumulate(grouped[(label, m["tournament"])], view)
    out = [
        {"player": player, "tournament": tournament, **_finalise(stat)}
        for (player, tournament), stat in grouped.items()
    ]
    out.sort(key=lambda r: (r["player"], r["tournament"]))
    return out

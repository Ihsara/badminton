"""Merge a draw bracket and the order-of-play into one friend's projected path.

Pure functions over the dicts produced by upcoming_parse — no network. The path
is the spine of the timeline UI: one node per round from the friend's current
position up to the Final, each tagged done/scheduled/projected so the frontend
can render decaying confidence honestly (no invented names or precise times).
"""

from __future__ import annotations

import re

_NAMED = {
    "final": "Final",
    "semi final": "SF", "semifinal": "SF", "semfinal": "SF",
    "quarter final": "QF", "quarterfinal": "QF",
}
_NUM_RE = re.compile(r"(\d+)")


def normalize_round(label: str) -> str:
    s = (label or "").strip().lower()
    if s in _NAMED:
        return _NAMED[s]
    if s.startswith(("kierros", "round")):
        m = _NUM_RE.search(s)
        if m:
            n = m.group(1)
            # "Round of 32" / "Kierros 32" -> R32
            return f"R{n}"
    m = _NUM_RE.search(s)
    return f"R{m.group(1)}" if m else (label or "").strip()


def _name_matches(friend: str, names: list[str]) -> bool:
    f = friend.strip().lower()
    return any(f == n.strip().lower() for n in names)


def _opponent(friend: str, names: list[str]) -> str | None:
    f = friend.strip().lower()
    others = [n for n in names if n.strip().lower() != f and n.strip().lower() != "bye"]
    return others[0] if others else None


def build_path(rounds: list[dict], schedule: list[dict], friend: str,
               event: str, today_iso: str) -> list[dict]:
    # Index schedule rows by normalized round for this event.
    sched_by_round: dict[str, dict] = {}
    for row in schedule:
        if row.get("event") and row["event"] != event:
            continue
        if not _name_matches(friend, row.get("players", [])):
            continue
        sched_by_round[normalize_round(row["round_label"])] = row

    path: list[dict] = []
    prev_round: str | None = None
    friend_seen = False
    for r in rounds:
        rnd = normalize_round(r["round_label"])
        srow = sched_by_round.get(rnd)
        slot_has_friend = _name_matches(friend, r.get("slots", []))
        if slot_has_friend:
            friend_seen = True

        node = {"round": rnd, "state": "projected", "opponent": None,
                "result": None, "court": None, "time": None,
                "time_kind": None, "day": None, "session": None}

        if srow and srow.get("result"):
            node["state"] = "done"
            node["result"] = srow["result"]
            node["opponent"] = _opponent(friend, srow.get("players", []))
            node["court"] = srow.get("court")
            node["time"] = _compose_time(srow)
            node["time_kind"] = "exact"
        elif srow:
            node["state"] = "scheduled"
            node["opponent"] = _opponent(friend, srow.get("players", []))
            node["court"] = srow.get("court")
            node["time"] = _compose_time(srow)
            node["time_kind"] = srow.get("time_kind") or "exact"
        elif slot_has_friend and r.get("scheduled_iso"):
            node["state"] = "scheduled"
            node["opponent"] = _opponent(friend, r.get("slots", []))
            node["time"] = r["scheduled_iso"]
            node["time_kind"] = "exact"
        else:
            # No concrete info: projected. Name opponent generically only if the
            # friend has already entered the bracket (so this round really is theirs).
            node["state"] = "projected"
            node["opponent"] = f"Winner of {prev_round}" if (friend_seen and prev_round) else None
            node["day"] = r.get("scheduled_iso", None) and r["scheduled_iso"][:10]

        path.append(node)
        prev_round = rnd
    return path


def _compose_time(srow: dict) -> str | None:
    """Combine the day ('2026-03-14') and 'HH.MM' clock into an ISO string."""
    t = srow.get("time")
    d = srow.get("date")
    if not t or not d:
        return None
    hh, _, mm = t.replace(".", ":").partition(":")
    try:
        return f"{d}T{int(hh):02d}:{int(mm or 0):02d}:00"
    except ValueError:
        return None

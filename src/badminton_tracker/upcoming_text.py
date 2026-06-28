"""Chat-friendly plaintext export of the upcoming timeline.

Pure function so it can be unit-tested as the canonical spec; the frontend's
formatChatText (app.js) mirrors this output. Honors the user's chosen filters
(players, tournaments) and options (horizon, fields).
"""

from __future__ import annotations


def _clock(iso: str | None, not_before: bool) -> str:
    if not iso:
        return ""
    hhmm = iso[11:16] if len(iso) >= 16 else ""
    return ("~" + hhmm) if (not_before and hhmm) else hhmm


def _line(player: str, event: str, node: dict, fields: set[str]) -> str:
    parts = [f"{player} ({event}): {node['round']}"]
    if node["state"] in ("scheduled", "done"):
        clk = _clock(node.get("time"), node.get("time_kind") == "not_before")
        if clk:
            parts.append(clk)
        if "court" in fields and node.get("court"):
            parts.append(f"Court {node['court']}")
        if "opponent" in fields and node.get("opponent"):
            parts.append(f"vs {node['opponent']}")
    else:  # projected
        when = node.get("session") or node.get("day") or ""
        opp = node.get("opponent") or "TBD"
        parts.append(f"{opp} ({when})".strip())
    return " ".join(parts)


def _first_relevant(path: list[dict], horizon: str) -> list[dict]:
    upcoming = [n for n in path if n["state"] in ("scheduled", "projected")]
    if horizon == "next":
        for n in upcoming:
            if n["state"] == "scheduled":
                return [n]
        return upcoming[:1]
    return upcoming


def format_chat_text(upcoming: dict, options: dict) -> str:
    players = options.get("players")
    tours = options.get("tournaments")
    horizon = options.get("horizon", "next")
    fields = set(options.get("fields") or {"court", "opponent"})
    show_projected = "projected" in fields or horizon == "full"

    out: list[str] = []
    for t in upcoming.get("tournaments", []):
        if tours and t["name"] not in tours:
            continue
        lines: list[str] = []
        for e in t.get("entries", []):
            if players and e["player"] not in players:
                continue
            nodes = _first_relevant(e["path"], horizon)
            for n in nodes:
                if n["state"] == "projected" and not show_projected:
                    continue
                lines.append(_line(e["player"], e["event"], n, fields))
        if lines:
            out.append(f"🏸 {t['name']}")
            out.extend(lines)
    return "\n".join(out)

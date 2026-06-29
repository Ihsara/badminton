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


def _line(player: str, event: str, node: dict, fields: set[str],
          partner: str | None = None) -> str:
    head = f"{player} ({event})"
    if partner:
        head = f"{player} (w/ {partner}) ({event})"
    parts = [f"{head}: {node['round']}"]
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


def _match_sig(event: str, node: dict) -> tuple[str, str, str]:
    """Identity of a physical match within a tournament. Two tracked friends
    partnering each other produce two entries with the same (event, time,
    opponent), so this signature lets us collapse them into one."""
    return (event, node.get("time") or "", node.get("opponent") or "")


def _partner_of(node: dict, label: str) -> str | None:
    """The partner to surface on a single-player match, or None. Skips the case
    where the recorded partner is just the player under another name (the label
    already covers them)."""
    partner = (node.get("partner") or "").strip()
    if not partner or partner == label:
        return None
    return partner


def _shared_players(entries: list[dict], event: str, node: dict) -> list[str]:
    """All tracked players whose path contains a node matching this match
    signature, sorted. A single-player match returns just that player."""
    sig = _match_sig(event, node)
    found = {
        e["player"]
        for e in entries
        for n in e.get("path", [])
        if _match_sig(e.get("event", ""), n) == sig
    }
    return sorted(found)


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
        entries = t.get("entries", [])
        # Collect (sort_key, line) so lines can be ordered chronologically
        # within the tournament — entries arrive in scrape order, not by time.
        # Scheduled/done sort by their time; projected nodes (no precise time)
        # sort after, by day/session.
        rows: list[tuple[tuple[int, str], str]] = []
        seen: set[tuple[str, tuple[str, str, str]]] = set()
        for e in entries:
            if players and e["player"] not in players:
                continue
            nodes = _first_relevant(e["path"], horizon)
            for n in nodes:
                if n["state"] == "projected" and not show_projected:
                    continue
                # Collapse a match shared by two tracked friends into one line,
                # attributed to the pair. Projected nodes have no stable
                # opponent/time signature, so leave them per-player.
                partner = None
                if n["state"] in ("scheduled", "done"):
                    shared = [p for p in _shared_players(entries, e["event"], n)
                              if not players or p in players]
                    key = (e["event"], _match_sig(e["event"], n))
                    if key in seen:
                        continue
                    seen.add(key)
                    label = " / ".join(shared) if shared else e["player"]
                    sort_key = (0, n.get("time") or "")
                    # Name the partner only when the label is a single player —
                    # a tracked pair ("Chau / Vu Luu") already names both.
                    if len(shared) <= 1:
                        partner = _partner_of(n, label)
                else:
                    label = e["player"]
                    sort_key = (1, n.get("day") or n.get("session") or "")
                rows.append((sort_key, _line(label, e["event"], n, fields, partner)))
        if rows:
            rows.sort(key=lambda r: r[0])
            out.append(f"🏸 {t['name']}")
            out.extend(line for _, line in rows)
    return "\n".join(out)


def next_match_per_player(upcoming: dict) -> list[dict]:
    """One row per (tournament, player) = that player's earliest still-scheduled
    match, sorted by time then player. Players with no scheduled node are omitted.
    Mirrors the frontend's nextMatchPerPlayer in app.js."""
    rows: list[dict] = []
    for t in upcoming.get("tournaments", []):
        entries = t.get("entries", [])
        seen: set[tuple[str, tuple[str, str, str]]] = set()
        for e in entries:
            scheduled = [n for n in e.get("path", []) if n.get("state") == "scheduled"]
            if not scheduled:
                continue
            node = min(scheduled, key=lambda n: n.get("time") or "")
            event = e.get("event", "")
            # Collapse a match shared by two tracked friends into one row,
            # attributed to the pair (sorted, " / "-joined).
            key = (event, _match_sig(event, node))
            if key in seen:
                continue
            seen.add(key)
            shared = _shared_players(entries, event, node)
            is_pair = len(shared) > 1
            label = " / ".join(shared) if is_pair else e.get("player", "")
            rows.append({
                "tournament": t.get("name", ""),
                "tournament_guid": t.get("tournament_guid"),
                "player": label,
                # Untracked partner (e.g. Nga Pham); None for a tracked pair,
                # which already names both players.
                "partner": None if is_pair else _partner_of(node, label),
                "event": event,
                "node": node,
            })
    rows.sort(key=lambda r: (r["node"].get("time") or "", r["player"]))
    return rows

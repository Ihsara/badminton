"""Export the group's data to web/data.json for the static explorer."""

from __future__ import annotations

import datetime as dt
import hashlib
import json

from . import aliases
from .config import ROOT
from .excel_source import friend_names, read_data_matches
from .stats import player_stats, tournament_stats

WEB_DIR = ROOT / "web"
DATA_JSON = WEB_DIR / "data.json"

GROUP_NAME = "Badminton Bros"


def _canonical_key(m: dict) -> tuple:
    """A side-independent identity for a match payload.

    Two rows describing the same physical match — including the same match
    logged from each side's perspective — produce the same key: the two teams
    are unordered, and each team's score is paired with its team so a side-swap
    (own/opp flip) collapses to the same value.
    """
    t1 = tuple(sorted(m["team1"]))
    t2 = tuple(sorted(m["team2"]))
    s1 = tuple(a for a, _ in m["sets"])
    s2 = tuple(b for _, b in m["sets"])
    side1 = (t1, s1)
    side2 = (t2, s2)
    teams = tuple(sorted((side1, side2)))
    return (m["date"], m["tournament"], m["category"], m["level"], m["round"], teams)


def match_id(m: dict) -> str:
    """Stable, side-independent id for a match (12 hex chars).

    Deterministic from the match's identity, so the same match always routes to
    the same #/match/<id> regardless of which side logged it.
    """
    raw = repr(_canonical_key(m)).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:12]


def dedupe_matches(payloads: list[dict]) -> tuple[list[dict], list[dict]]:
    """Collapse rows that are the same physical match logged from both sides.

    Conservative by design: only rows with an identical canonical key (same
    date/tournament/category/level/round, same two teams, and identical scores
    once the side-swap is accounted for) are merged. Different brackets or
    different scores are kept as separate matches — a genuine rematch survives.

    Returns (kept, removed) where `kept` preserves first-occurrence order and
    `removed` lists the dropped duplicate payloads (for a build-time warning).
    """
    seen: dict[tuple, dict] = {}
    kept: list[dict] = []
    removed: list[dict] = []
    for m in payloads:
        key = _canonical_key(m)
        if key in seen:
            removed.append(m)
        else:
            seen[key] = m
            kept.append(m)
    return kept, removed


def _sets(m: dict) -> list[list[int]]:
    out = []
    for own, opp in (
        (m["set_1_own"], m["set_1_opp"]),
        (m["set_2_own"], m["set_2_opp"]),
        (m["set_3_own"], m["set_3_opp"]),
    ):
        if isinstance(own, int) and isinstance(opp, int):
            out.append([own, opp])
    return out


def _match_payload(m: dict) -> dict:
    p = {
        "date": m["date"],
        "tournament": m["tournament"],
        "category": m["category"],
        "level": m["level"],
        "round": m["round"],
        "team1": [p for p in (m["player_1"], m["player_2"]) if p],
        "team2": [p for p in (m["opponent_1"], m["opponent_2"]) if p],
        "result": m["result"],
        "sets": _sets(m),
    }
    p["id"] = match_id(p)
    return p


def _warn_duplicates(removed: list[dict]) -> None:
    print(f"⚠ Collapsed {len(removed)} duplicate match row(s) (same match logged twice):")
    for m in removed:
        t1 = " / ".join(m["team1"]) or "?"
        t2 = " / ".join(m["team2"]) or "?"
        scores = " ".join(f"{a}-{b}" for a, b in m["sets"])
        meta = f"[{m['category']} {m['level']} {m['round']}]"
        print(f"    · {m['date']} {m['tournament']} {meta} {t1} vs {t2} ({scores})")
    print("    Fix the workbook to drop the extra row(s); counts use the de-duplicated set.")


def build_payload(matches: list[dict], roster: list[dict], source: str) -> dict:
    # De-duplicate once, on the payloads (which carry the canonical identity),
    # then map the survivors back to their internal dicts so stats are computed
    # on the same set — a match logged from both sides counts once for everyone.
    pairs = [(m, _match_payload(m)) for m in matches]
    payloads, removed = dedupe_matches([p for _, p in pairs])
    if removed:
        _warn_duplicates(removed)
    kept_ids = {p["id"] for p in payloads}
    seen: set[str] = set()
    deduped = []
    for raw, p in pairs:
        if p["id"] in kept_ids and p["id"] not in seen:
            seen.add(p["id"])
            deduped.append(raw)

    pstats = player_stats(deduped, roster)
    tstats = tournament_stats(deduped, roster)
    tournaments = sorted({m["tournament"] for m in deduped if m["tournament"]})
    return {
        "group_name": GROUP_NAME,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "counts": {
            "players": len(pstats),
            "matches": len(payloads),
            "tournaments": len(tournaments),
        },
        "players": pstats,
        "tournaments_list": tournaments,
        "player_tournament": tstats,
        "matches": payloads,
    }


def roster_from_names(names: list[str]) -> list[dict]:
    return [{"nickname": n, "full_name": n} for n in names]


def _match_names(m: dict) -> list[str]:
    return [m["player_1"], m["player_2"], m["opponent_1"], m["opponent_2"]]


def apply_aliases(matches: list[dict], mapping: dict[str, str] | None = None) -> list[dict]:
    """Replace each recorded name with its chosen display nickname.

    The mapping is GUID-free — the private nickname→real-name→profile linkage
    never reaches data.json. Applied to every name on the court (friends and
    their opponents), so a relabel shows up everywhere. Case-only duplicates
    (e.g. "Paphon KASEMVUDHI") are folded to one canonical spelling first.
    """
    mapping = aliases.alias_map() if mapping is None else mapping
    all_names = [m[k] for m in matches
                 for k in ("player_1", "player_2", "opponent_1", "opponent_2")]
    casefold = aliases.casefold_merge_map(all_names)
    out = []
    for m in matches:
        mm = dict(m)
        for key in ("player_1", "player_2", "opponent_1", "opponent_2"):
            folded = casefold.get(m[key], m[key])
            mm[key] = aliases.apply(folded, mapping)
        out.append(mm)
    return out


def export_json(matches: list[dict], roster: list[dict], source: str) -> None:
    WEB_DIR.mkdir(exist_ok=True)
    payload = build_payload(matches, roster, source)
    DATA_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    c = payload["counts"]
    print(
        f"Wrote {DATA_JSON} — {c['matches']} matches, "
        f"{c['players']} players, {c['tournaments']} tournaments"
    )


def export_from_excel() -> None:
    """Build the public explorer data from the workbook, with nicknames applied.

    The roster (who gets a stats page / appears in standings) stays the friend
    group — the names on the Player 1/2 side of the log. The nickname editor is
    seeded with exactly that group, while aliases still display on every name.
    """
    friends = friend_names()
    aliases.ensure_names(friends)  # seed the editor with the group
    mapping = aliases.alias_map()
    matches = apply_aliases(read_data_matches(), mapping)
    # Fold case-only twins (e.g. "Paphon KASEMVUDHI") to one spelling, then apply
    # explicit aliases, so a person gets a single stats page — not one row per
    # spelling. Preserve order.
    casefold = aliases.casefold_merge_map(friends)
    display_names = list(dict.fromkeys(
        aliases.apply(casefold.get(f, f), mapping) for f in friends))
    roster = roster_from_names(display_names)
    export_json(matches, roster, source="excel")


if __name__ == "__main__":
    export_from_excel()

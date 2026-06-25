"""Export the group's data to web/data.json for the static explorer."""

from __future__ import annotations

import datetime as dt
import json

from . import aliases
from .config import ROOT
from .excel_source import friend_names, read_data_matches
from .stats import player_stats, tournament_stats

WEB_DIR = ROOT / "web"
DATA_JSON = WEB_DIR / "data.json"

GROUP_NAME = "Badminton Bros"


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
    return {
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


def build_payload(matches: list[dict], roster: list[dict], source: str) -> dict:
    pstats = player_stats(matches, roster)
    tstats = tournament_stats(matches, roster)
    tournaments = sorted({m["tournament"] for m in matches if m["tournament"]})
    return {
        "group_name": GROUP_NAME,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "counts": {
            "players": len(pstats),
            "matches": len(matches),
            "tournaments": len(tournaments),
        },
        "players": pstats,
        "tournaments_list": tournaments,
        "player_tournament": tstats,
        "matches": [_match_payload(m) for m in matches],
    }


def roster_from_names(names: list[str]) -> list[dict]:
    return [{"nickname": n, "full_name": n} for n in names]


def _match_names(m: dict) -> list[str]:
    return [m["player_1"], m["player_2"], m["opponent_1"], m["opponent_2"]]


def apply_aliases(matches: list[dict], mapping: dict[str, str] | None = None) -> list[dict]:
    """Replace each recorded name with its chosen display nickname.

    The mapping is GUID-free — the private nickname→real-name→profile linkage
    never reaches data.json. Applied to every name on the court (friends and
    their opponents), so a relabel shows up everywhere.
    """
    mapping = aliases.alias_map() if mapping is None else mapping
    out = []
    for m in matches:
        mm = dict(m)
        for key in ("player_1", "player_2", "opponent_1", "opponent_2"):
            mm[key] = aliases.apply(m[key], mapping)
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
    roster = roster_from_names([aliases.apply(f, mapping) for f in friends])
    export_json(matches, roster, source="excel")


if __name__ == "__main__":
    export_from_excel()

"""Fetch every confirmed friend's matches and merge into a deduplicated match log."""

from __future__ import annotations

import csv

from playwright.sync_api import sync_playwright

from .client import dismiss_cookies, ensure_login, new_context
from .config import BASE_URL, PLAYERS_CSV
from .parse import extract_player_matches


def load_players() -> list[dict]:
    """Read players.csv, keeping rows the user marked to include with a GUID."""
    if not PLAYERS_CSV.exists():
        raise FileNotFoundError(f"{PLAYERS_CSV} not found — run discovery and confirm it first")
    players = []
    with open(PLAYERS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            guid = (row.get("profile_guid") or "").strip()
            include = (row.get("include") or "").strip().lower()
            if guid and include in ("y", "yes", "1", "true", "x"):
                players.append(
                    {
                        "nickname": (row.get("nickname") or "").strip(),
                        "full_name": (row.get("full_name") or "").strip(),
                        "guid": guid,
                    }
                )
    return players


def _match_key(m: dict) -> tuple:
    """Identity of a match, independent of which friend's profile it came from.

    Both friends in a friend-vs-friend match report it; sorting the four player
    names makes those two reports collapse to one row.
    """
    players = tuple(
        sorted(
            n.lower()
            for n in (m["player_1"], m["player_2"], m["opponent_1"], m["opponent_2"])
            if n
        )
    )
    return (m["date"], m["tournament"], m["category"], m["round"], players)


def fetch_all() -> list[dict]:
    players = load_players()
    if not players:
        raise RuntimeError(
            "No players marked include=Y with a GUID in players.csv — confirm it first"
        )

    merged: dict[tuple, dict] = {}
    with sync_playwright() as p:
        browser, ctx = new_context(p)
        page = ensure_login(ctx)
        for pl in players:
            name = pl["full_name"] or pl["nickname"]
            print(f"Fetching {name} ({pl['guid'][:8]}…)")
            page.goto(
                f"{BASE_URL}/player-profile/{pl['guid']}/tournaments",
                wait_until="domcontentloaded",
            )
            dismiss_cookies(page)
            page.wait_for_timeout(1200)
            rows = extract_player_matches(page, name)
            for m in rows:
                # Prefer the friend's own nickname in the Player columns where known.
                m["_source"] = pl["nickname"] or name
                merged.setdefault(_match_key(m), m)
            print(f"  +{len(rows)} matches (total unique: {len(merged)})")
        browser.close()
    return list(merged.values())


if __name__ == "__main__":
    out = fetch_all()
    print(f"\n{len(out)} unique matches fetched")

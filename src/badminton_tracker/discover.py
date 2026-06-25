"""Auto-discover the friend group's player profiles by snowballing the match graph.

Starting from the logged-in user, walk partners and opponents outward, resolve each
name to a /player-profile GUID, and write a `players.csv` for the user to confirm.
"""

from __future__ import annotations

import csv
from collections import defaultdict

from playwright.sync_api import sync_playwright

from .client import dismiss_cookies, ensure_login, new_context
from .config import BASE_URL
from .excel_source import friend_names
from .parse import _norm_tokens, extract_player_matches
from .roster import CANDIDATES_CSV, build_players_csv
from .search import resolve_name

ME_NAME = "Long Chau Tran"
ME_GUID = "d69f71b9-69f2-472e-97b2-4fc80ac43a17"

# Profiles to fetch when expanding the graph; keeps discovery bounded.
MAX_FETCHES = 40


def _names_in_match(m: dict) -> list[tuple[str, str]]:
    """Return (name, role) for every named player in a parsed match row."""
    out = []
    for key, role in (
        ("player_2", "partner"),
        ("opponent_1", "opponent"),
        ("opponent_2", "opponent"),
        ("player_1", "partner"),
    ):
        n = m.get(key)
        if n:
            out.append((n, role))
    return out


def _load_profile(page, guid: str) -> list[dict]:
    page.goto(f"{BASE_URL}/player-profile/{guid}/tournaments", wait_until="domcontentloaded")
    dismiss_cookies(page)
    page.wait_for_timeout(1200)
    return extract_player_matches(page, "")


def _guess_nickname(canonical: str, nick_index: dict[str, str]) -> str:
    """Match a discovered full name to an Excel nickname by shared name tokens."""
    toks = _norm_tokens(canonical)
    for tok in toks:
        if tok in nick_index:
            return nick_index[tok]
    return ""


def discover(max_depth: int = 2) -> None:
    nicknames = friend_names()
    # Index Excel nicknames/full names by their lowercased tokens for fuzzy matching.
    nick_index: dict[str, str] = {}
    for n in nicknames:
        for tok in _norm_tokens(n):
            nick_index.setdefault(tok, n)

    counts: dict[str, int] = defaultdict(int)
    roles: dict[str, set[str]] = defaultdict(set)
    display: dict[str, str] = {}
    resolve_cache: dict[str, tuple[str, str] | None] = {}

    def resolve_cached(page, name: str):
        key = name.lower()
        if key not in resolve_cache:
            resolve_cache[key] = resolve_name(page, name)
        return resolve_cache[key]

    with sync_playwright() as p:
        browser, ctx = new_context(p)
        page = ensure_login(ctx)

        frontier = [(ME_NAME, ME_GUID)]
        visited: set[str] = set()
        fetches = 0

        for depth in range(max_depth):
            next_frontier: list[tuple[str, str]] = []
            for owner_name, guid in frontier:
                if guid.lower() in visited or fetches >= MAX_FETCHES:
                    continue
                visited.add(guid.lower())
                fetches += 1
                print(f"[depth {depth}] fetching {owner_name} ({guid[:8]}…)")
                matches = _load_profile(page, guid)
                owner_tokens = _norm_tokens(owner_name)
                seen_here: set[str] = set()
                for m in matches:
                    for name, role in _names_in_match(m):
                        if owner_tokens & _norm_tokens(name):
                            continue
                        key = name.lower()
                        display.setdefault(key, name)
                        roles[key].add(role)
                        if key not in seen_here:
                            counts[key] += 1
                            seen_here.add(key)

                # Resolve the strongest new names and queue them for the next hop.
                if depth + 1 < max_depth:
                    ranked = sorted(seen_here, key=lambda k: counts[k], reverse=True)
                    for key in ranked[:12]:
                        if counts[key] < 1:
                            continue
                        resolved = resolve_cached(page, display[key])
                        if resolved and resolved[1].lower() not in visited:
                            next_frontier.append((resolved[0], resolved[1]))
            frontier = next_frontier

        # Resolve GUIDs for every candidate for the final table.
        rows = []
        for key in sorted(counts, key=lambda k: counts[k], reverse=True):
            name = display[key]
            resolved = resolve_cached(page, name)
            guid = resolved[1] if resolved else ""
            canonical = resolved[0] if resolved else name
            rows.append(
                {
                    "nickname": _guess_nickname(canonical, nick_index),
                    "full_name": canonical,
                    "profile_guid": guid,
                    "profile_url": f"{BASE_URL}/player-profile/{guid}" if guid else "",
                    "appearances": counts[key],
                    "roles": ",".join(sorted(roles[key])),
                    "include": "",
                }
            )
        browser.close()

    with open(CANDIDATES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "nickname",
                "full_name",
                "profile_guid",
                "profile_url",
                "appearances",
                "roles",
                "include",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} candidates -> {CANDIDATES_CSV}")
    build_players_csv()


if __name__ == "__main__":
    discover()

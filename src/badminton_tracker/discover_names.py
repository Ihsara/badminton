"""Name-based discovery drivers (live; manually verified — see rule #6).

Source A (cheap, runs freely): walk confirmed friends' player-profile match pages
and harvest the partner/opponent names beside them.
Source B (ban-risky, gated): for explicitly-named tournaments, scan the
participant list. Defaults to a DRY RUN that only prints what it would fetch;
pass go=True (CLI --go) to actually scrape, throttled and page-capped.

All harvested names go through discovery_queue.split_sightings, so nothing is
auto-linked to a person. Drivers are # pragma: no cover; the matching logic they
feed is unit-tested in test_discovery_queue.py.
"""

from __future__ import annotations

from . import identity
from .config import BASE_URL
from .discovery_queue import load_queue, split_sightings, write_queue


def harvest_from_friends() -> list[dict]:  # pragma: no cover - live driver
    from playwright.sync_api import sync_playwright

    from .client import ensure_login, new_context
    from .discover import _load_profile, _names_in_match
    from .fetch import load_players

    players = load_players()
    sightings: list[dict] = []
    with sync_playwright() as p:
        browser, ctx = new_context(p)
        page = ensure_login(ctx)
        for pl in players:
            owner = pl["nickname"] or pl["full_name"]
            print(f"[friends] harvesting {owner} ({pl['guid'][:8]}…)")
            for m in _load_profile(page, pl["guid"]):
                for name, role in _names_in_match(m):
                    sightings.append({"seen_name": name, "kind": role,
                                      "where_seen": f"{owner}'s profile", "alongside": owner})
            page.wait_for_timeout(800)  # politeness
        browser.close()
    return sightings


def scan_participants(tournament_guids, go, max_pages) -> list[dict]:  # pragma: no cover
    guids = list(tournament_guids or [])
    if not go:
        print("DRY RUN — would fetch participant lists for:")
        for g in guids:
            print(f"  {BASE_URL}/tournament/{g}/participants")
        print(f"(max_pages={max_pages}) Re-run with --go to actually scrape.")
        return []

    from playwright.sync_api import sync_playwright

    from .client import dismiss_cookies, ensure_login, new_context

    sightings: list[dict] = []
    with sync_playwright() as p:
        browser, ctx = new_context(p)
        page = ensure_login(ctx)
        for page_idx, g in enumerate(guids):
            if page_idx >= max_pages:
                print(f"[participants] max_pages={max_pages} reached; stopping.")
                break
            url = f"{BASE_URL}/tournament/{g}/participants"
            print(f"[participants] fetching {url}")
            page.goto(url, wait_until="domcontentloaded")
            dismiss_cookies(page)
            page.wait_for_timeout(1200)  # throttle
            for a in page.query_selector_all("a[href*=player]"):
                name = (a.inner_text() or "").strip()
                if name and len(name) > 2:
                    sightings.append({"seen_name": name, "kind": "participant",
                                      "where_seen": f"tournament {g}", "alongside": ""})
        browser.close()
    return sightings


def run_discover_names(tournament_guids=None, go=False, max_pages=20) -> int:  # pragma: no cover
    sightings = harvest_from_friends()
    sightings += scan_participants(tournament_guids, go, max_pages)

    aliases = identity.load_person_aliases()
    known = identity.known_alias_names(aliases)
    existing_queue = load_queue()
    queued = {r["seen_name"].lower() for r in existing_queue}

    known_hits, new_candidates = split_sightings(sightings, known, queued)
    write_queue(existing_queue + new_candidates)
    print(f"{len(known_hits)} known sighting(s) (silent); "
          f"{len(new_candidates)} new candidate(s) -> data/discovery_candidates.csv. "
          "Review, fill `decision`, then run: badminton identity-confirm.")
    return len(new_candidates)

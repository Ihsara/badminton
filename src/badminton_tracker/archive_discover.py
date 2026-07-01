"""Discover finished-tournament GUIDs from core friends' profile pages.

The profile page is server-rendered, so a plain fetch (the injected fetch_fn,
which applies the raw-cache + politeness of archive_fetch) suffices. Pure union
logic is unit-tested; the live wiring lives in archive_crawl.crawl_from_profiles.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from . import archive_profile
from .config import DATA_DIR


def core_profile_guids(csv_path: Path | None = None) -> list[str]:
    path = csv_path or (DATA_DIR / "players.csv")
    if not path.exists():
        return []
    guids: list[str] = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            g = (row.get("profile_guid") or "").strip()
            if g:
                guids.append(g)
    return guids


def discover_tournament_ids(fetch_fn, profile_guids, base_url) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for guid in profile_guids:
        try:
            html = fetch_fn(f"{base_url}/player-profile/{guid}")
            tours = archive_profile.parse_profile_tournaments(html)
        except Exception as e:  # noqa: BLE001 — one bad profile must not abort discovery
            print(f"discover_tournament_ids: skipping profile {guid}: {e}", file=sys.stderr)
            continue
        for t in tours:
            key = t["id"].lower()
            if key not in seen:
                seen.add(key)
                out.append(t)
    return out

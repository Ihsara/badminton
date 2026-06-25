"""Turn raw discovery candidates into a clean, friend-centric players.csv.

One row per Excel friend nickname. A profile GUID is auto-filled only when a
discovered candidate is a *strong* name match (all tokens of the shorter name
shared), so weak same-token collisions are left blank for manual confirmation.
"""

from __future__ import annotations

import csv
import unicodedata

from .config import PLAYERS_CSV, ROOT
from .excel_source import friend_names

CANDIDATES_CSV = ROOT / "players_candidates.csv"

FIELDS = ["nickname", "full_name", "profile_guid", "profile_url", "confidence", "include"]


def _fold(s: str) -> set[str]:
    norm = unicodedata.normalize("NFKD", s.lower())
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    return {t for t in norm.replace(".", " ").split() if t}


def _load_candidates() -> list[dict]:
    if not CANDIDATES_CSV.exists():
        return []
    with open(CANDIDATES_CSV, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("profile_guid") or "").strip()]
    for r in rows:
        try:
            r["_app"] = int(r.get("appearances") or 0)
        except ValueError:
            r["_app"] = 0
    return rows


def _best_match(name: str, candidates: list[dict]) -> tuple[dict | None, str]:
    """Return (candidate, confidence) for the strongest match to `name`."""
    target = _fold(name)
    if not target:
        return None, "none"
    multi = len(target) > 1
    strong: list[dict] = []
    weak: list[dict] = []
    for c in candidates:
        # Match only on the resolved real name; the candidate's own "nickname"
        # column is a prior (possibly wrong) guess and must not be trusted here.
        cand_tokens = _fold(c.get("full_name") or "")
        if not cand_tokens:
            continue
        if multi and target <= cand_tokens:
            strong.append(c)  # every word of the friend's name is present
        elif not multi and target & cand_tokens:
            weak.append(c)  # single-token nickname shares a name part
    if strong:
        return max(strong, key=lambda c: c["_app"]), "high"
    if weak:
        return max(weak, key=lambda c: c["_app"]), "low"
    return None, "none"


def build_players_csv() -> None:
    candidates = _load_candidates()
    rows = []
    filled = 0
    for name in friend_names():
        match, conf = _best_match(name, candidates)
        guid = (match.get("profile_guid") if match else "") or ""
        if guid:
            filled += 1
        # Pre-fill any guess; only auto-include high-confidence ones. The user
        # flips `include` to Y after eyeballing the low-confidence guesses.
        rows.append(
            {
                "nickname": name,
                "full_name": (match.get("full_name") if match else "") or "",
                "profile_guid": guid,
                "profile_url": (match.get("profile_url") if match else "") or "",
                "confidence": conf,
                "include": "Y" if conf == "high" else "",
            }
        )

    with open(PLAYERS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(
        f"Wrote {len(rows)} friend rows -> {PLAYERS_CSV} "
        f"({filled} auto-filled with high confidence; the rest need a profile URL)."
    )


if __name__ == "__main__":
    build_players_csv()

"""Friend-editable name → nickname mapping (data/aliases.csv).

The match log uses whatever name each player is recorded under (a mix of
nicknames like "Tong" and full names like "Nga Pham"). This layer lets the
group map any of those to a friendly display nickname without touching the
workbook. The file auto-grows: every name seen in the data gets a row, so the
web editor always shows the full cast for friends to relabel.
"""

from __future__ import annotations

import csv

from .config import ALIASES_CSV

FIELDS = ["name", "display", "notes"]


def load_aliases() -> list[dict]:
    if not ALIASES_CSV.exists():
        return []
    with open(ALIASES_CSV, encoding="utf-8", newline="") as f:
        rows = []
        for r in csv.DictReader(f):
            rows.append(
                {
                    "name": (r.get("name") or "").strip(),
                    "display": (r.get("display") or "").strip(),
                    "notes": (r.get("notes") or "").strip(),
                }
            )
    return [r for r in rows if r["name"]]


def write_aliases(rows: list[dict]) -> None:
    ALIASES_CSV.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: r["name"].casefold())
    with open(ALIASES_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def alias_map() -> dict[str, str]:
    """name → display, only for rows that actually assign a nickname."""
    return {r["name"]: r["display"] for r in load_aliases() if r["display"]}


def casefold_merge_map(names: list[str]) -> dict[str, str]:
    """Map each name that differs from another only by letter-case to one
    canonical spelling, so case-only duplicates (e.g. "Paphon Kasemvudhi" and
    "Paphon KASEMVUDHI") collapse to a single person. The canonical spelling is
    the variant with the most lowercase letters (proper-case beats ALL-CAPS),
    ties broken by first appearance. Names with no case-twin are omitted."""
    groups: dict[str, list[str]] = {}
    for n in names:
        if not n:
            continue
        groups.setdefault(n.casefold(), [])
        if n not in groups[n.casefold()]:
            groups[n.casefold()].append(n)

    def _lower_count(s: str) -> int:
        return sum(1 for c in s if c.islower())

    out: dict[str, str] = {}
    for variants in groups.values():
        if len(variants) < 2:
            continue
        canonical = max(variants, key=lambda s: (_lower_count(s), -variants.index(s)))
        for v in variants:
            out[v] = canonical
    return out


def apply(name: str, mapping: dict[str, str] | None = None) -> str:
    if not name:
        return name
    mapping = alias_map() if mapping is None else mapping
    return mapping.get(name, name)


def ensure_names(names: list[str]) -> bool:
    """Make sure every given name has a row in aliases.csv. Returns True if the
    file changed (so callers can decide whether to re-commit)."""
    existing = {r["name"] for r in load_aliases()}
    missing = [n for n in names if n and n not in existing]
    if not missing:
        return False
    rows = load_aliases()
    rows.extend({"name": n, "display": "", "notes": ""} for n in missing)
    write_aliases(rows)
    return True

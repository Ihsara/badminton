"""Load the private exclude list — names never matched as friends (rule: the
wrong Toni and Yuki Matti). Lives in data/exclude.csv (never published)."""

from __future__ import annotations

import csv
from pathlib import Path

from .config import EXCLUDE_CSV


def load_excludes(path: Path | None = None) -> set[str]:
    path = EXCLUDE_CSV if path is None else path
    if not path.exists():
        return set()
    out: set[str] = set()
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").strip().lower()
            if name:
                out.add(name)
    return out

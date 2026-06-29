"""The core friend group — display nicknames only (public-safe).

These are the people whose stats page should be shown prominently on the site.
Everyone else who appears on the Player side of the log is "peripheral" (an
occasional partner, a coach, a one-off). Nicknames are already public in
data.json, so this list carries no private identity data and is checked into
the public repo.
"""

from __future__ import annotations

CORE_NICKNAMES: frozenset[str] = frozenset({
    "Chau", "Dao", "Santeri", "Thy", "Maila",
    "Tong", "Junya", "Toni", "Matti", "Khai", "Boris",
})

_CORE_FOLDED = {n.casefold() for n in CORE_NICKNAMES}


def is_core(name: str) -> bool:
    """Case-insensitive membership test against the core group."""
    return bool(name) and name.casefold() in _CORE_FOLDED

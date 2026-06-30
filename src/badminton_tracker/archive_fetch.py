"""Fetch + content-addressed raw cache.

The HTTP getter is injected so the cache logic is testable without network;
the live driver supplies a Playwright getter.  Politeness (delay) lives here.

ARCHIVE_RAW_DIR is read from the config *module* (not bound at import time) so
that tests can monkeypatch `config.ARCHIVE_RAW_DIR` and have the patch honoured
inside cache_put / fetch.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from . import config


def _hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def cache_get(conn, url: str) -> str | None:
    """Return cached body text for *url*, or None if not cached (or file gone)."""
    row = conn.execute(
        "SELECT body_path FROM raw_cache WHERE url_hash=?", (_hash(url),)
    ).fetchone()
    if row is None:
        return None
    p = Path(row["body_path"])
    return p.read_text(encoding="utf-8") if p.exists() else None


def cache_put(conn, url: str, body: str, status_code: int, now: str) -> str:
    """Write *body* to a content-addressed file and record it in raw_cache.

    Returns the absolute path string of the written file.
    """
    raw_dir = Path(config.ARCHIVE_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    h = _hash(url)
    body_path = raw_dir / f"{h}.html"
    body_path.write_text(body, encoding="utf-8")
    conn.execute(
        """INSERT INTO raw_cache (url_hash, url, body_path, status_code, fetched_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(url_hash) DO UPDATE SET
             body_path=excluded.body_path,
             status_code=excluded.status_code,
             fetched_at=excluded.fetched_at""",
        (h, url, str(body_path), status_code, now),
    )
    conn.commit()
    return str(body_path)


def fetch(conn, url: str, getter, now: str, *, delay_ms: int = 700) -> str:
    """Return the HTML body for *url*, using the cache when available.

    If not cached:
    1. Sleep *delay_ms* ms (politeness).
    2. Call ``getter(url) -> (body: str, status_code: int)``.
    3. Store via :func:`cache_put`.
    4. Return body.

    Pass ``delay_ms=0`` in tests for instant execution.
    """
    cached = cache_get(conn, url)
    if cached is not None:
        return cached
    if delay_ms:
        time.sleep(delay_ms / 1000.0)
    body, status = getter(url)
    cache_put(conn, url, body, status, now)
    return body

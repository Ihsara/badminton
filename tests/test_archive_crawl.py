"""Tests for archive_fetch (Task 6) and archive crawl (Task 7+)."""

from datetime import UTC, datetime

from badminton_tracker import archive_crawl, archive_db, archive_fetch


def test_fetch_caches_and_does_not_refetch(tmp_path, monkeypatch):
    from badminton_tracker import config
    monkeypatch.setattr(config, "ARCHIVE_RAW_DIR", tmp_path / "raw")
    conn = archive_db.connect(tmp_path / "a.sqlite")
    calls = []

    def getter(url):
        calls.append(url)
        return ("<html>hi</html>", 200)

    b1 = archive_fetch.fetch(conn, "http://x/1", getter, now="t", delay_ms=0)
    b2 = archive_fetch.fetch(conn, "http://x/1", getter, now="t", delay_ms=0)
    assert b1 == b2 == "<html>hi</html>"
    assert calls == ["http://x/1"]  # second call served from cache
    conn.close()


# ---------------------------------------------------------------------------
# Task 7 - crawl state machine
# ---------------------------------------------------------------------------

def _fresh_conn():
    """In-memory SQLite connection with the archive schema applied."""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(archive_db.SCHEMA)
    conn.commit()
    return conn


def test_run_is_idempotent_and_resumable():
    """run() processes a tournament once; second run skips it (done==0), no dup matches."""
    conn = _fresh_conn()

    draws_html = (
        '<html><body>'
        '<a class="module__link" href="/sport/draw.aspx?id=T1&draw=1">MD</a>'
        '</body></html>'
    )

    bracket_html = (
        '<html><body><div class="bracket">'
        '<div class="bracket-round">'
        '<h4 class="bracket-round__title">Final</h4>'
        '<div class="bracket-round__match-group-wrapper">'
        '<div class="bracket-round__match-group">'
        '<div class="match__row has-won"><span class="nav-link__value">Alice</span></div>'
        '<div class="match__row"><span class="nav-link__value">Bob</span></div>'
        '</div></div></div></div>'
        '</body></html>'
    )

    def fake_fetch(url):
        if "draws.aspx" in url:
            return draws_html
        return bracket_html

    tournaments = [{"id": "T1", "name": "Test Cup", "starts": "2024-01-01"}]
    now = datetime(2024, 1, 10, tzinfo=UTC)

    result1 = archive_crawl.run(conn, tournaments, fake_fetch, now)
    assert result1["done"] == 1
    assert result1["error"] == 0

    cur = conn.execute("SELECT COUNT(*) FROM matches")
    count_after_first = cur.fetchone()[0]
    assert count_after_first == 1  # fake bracket has exactly one Final match
    # Alice has match__row has-won => winner_side == 1
    winner = conn.execute("SELECT winner_side FROM matches").fetchone()[0]
    assert winner == 1

    result2 = archive_crawl.run(conn, tournaments, fake_fetch, now)
    assert result2["done"] == 0  # T1 already done, skipped
    assert result2["error"] == 0

    cur = conn.execute("SELECT COUNT(*) FROM matches")
    count_after_second = cur.fetchone()[0]
    assert count_after_second == count_after_first  # no duplicates


def test_run_records_error_without_crashing():
    """When fetch raises, run() sets state=error, stores message, returns error==1."""
    conn = _fresh_conn()

    def bad_fetch(url):
        raise RuntimeError("network down")

    tournaments = [{"id": "T2", "name": "Crash Cup", "starts": "2024-02-01"}]
    now = datetime(2024, 2, 10, tzinfo=UTC)

    result = archive_crawl.run(conn, tournaments, bad_fetch, now)
    assert result["error"] == 1
    assert result["done"] == 0

    cur = conn.execute(
        "SELECT status, last_error FROM crawl_state WHERE tournament_id='T2'"
    )
    row = cur.fetchone()
    assert row["status"] == "error"
    assert "network down" in row["last_error"]

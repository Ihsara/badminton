"""Tests for archive_fetch (Task 6) and archive crawl (Task 7+)."""

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
# Task 7 — crawl state machine
# ---------------------------------------------------------------------------

_DRAWS_HTML = '<a class="module__link" href="/sport/draw.aspx?id=D&draw=1">MD</a>'

_BRACKET_HTML = (
    '<div class="bracket">'
    '<div class="bracket-round">'
    '<h4 class="bracket-round__title">Final</h4>'
    '<div class="bracket-round__match-group-wrapper">'
    '<div class="bracket-round__match-group">'
    '<div class="match__row has-won"><span class="nav-link__value">Alice</span></div>'
    '<div class="match__row"><span class="nav-link__value">Bob</span></div>'
    '</div></div></div></div>'
)


def _fake_fetch(url):
    if "draws" in url:
        return _DRAWS_HTML
    return _BRACKET_HTML


def test_run_is_idempotent_and_resumable(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")
    tlist = [{"id": "T1", "name": "Cup 2024", "start_date": "2024-04-12"}]
    r1 = archive_crawl.run(conn, tlist, _fake_fetch, now="t")
    assert r1["done"] == 1 and r1["error"] == 0
    n_matches_1 = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    # Re-run: T1 already done → skipped, no duplicate matches.
    r2 = archive_crawl.run(conn, tlist, _fake_fetch, now="t")
    assert r2["done"] == 0  # nothing re-processed
    n_matches_2 = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    assert n_matches_1 == n_matches_2
    conn.close()


def test_run_records_error_without_crashing(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")

    def boom(url):
        raise RuntimeError("network down")

    r = archive_crawl.run(
        conn,
        [{"id": "T9", "name": "X", "start_date": None}],
        boom,
        now="t",
    )
    assert r["error"] == 1
    row = conn.execute(
        "SELECT status, last_error FROM crawl_state WHERE tournament_id='T9'"
    ).fetchone()
    assert row["status"] == "error" and "network down" in row["last_error"]
    conn.close()

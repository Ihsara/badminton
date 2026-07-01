"""Tests for archive_fetch (Task 6) and archive crawl (Task 7+)."""

from pathlib import Path

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

_MATCHES_HTML = (Path(__file__).parent / "fixtures" / "archive" / "matches_page.html").read_text(
    encoding="utf-8"
)


def _fake_matches_fetch(url):
    assert "matches.aspx" in url
    return _MATCHES_HTML


def test_run_is_idempotent_and_resumable(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")
    tlist = [{"id": "T1", "name": "Cup 2024", "start_date": "2024-04-12"}]
    r1 = archive_crawl.run(conn, tlist, _fake_matches_fetch, now="t")
    assert r1["done"] == 1 and r1["error"] == 0
    n_matches_1 = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    # The fixture has exactly 2 matches; assert both parsed through (guards
    # against a vacuous pass if parsing silently yields zero matches).
    assert n_matches_1 == 2
    # A real parsed value survived (guard against vacuous pass).
    row = conn.execute(
        "SELECT winner_side FROM matches WHERE winner_side IS NOT NULL"
    ).fetchone()
    assert row is not None and row["winner_side"] is not None
    # Re-run: T1 already done → skipped, no duplicate matches.
    r2 = archive_crawl.run(conn, tlist, _fake_matches_fetch, now="t")
    assert r2["done"] == 0  # nothing re-processed
    n_matches_2 = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    assert n_matches_1 == n_matches_2
    conn.close()


def test_process_matches_tournament_stores_draws_players_matches(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")
    tid = "AAAA1111-1111-1111-1111-111111111111"
    archive_db.upsert_tournament(conn, {
        "id": tid, "name": "T", "year": 2025, "start_date": None, "end_date": None,
        "location": None, "region": None, "category": None,
        "source_url": "u", "fetched_at": "now",
    })
    fx = Path(__file__).parent / "fixtures" / "archive" / "matches_page.html"
    html = fx.read_text(encoding="utf-8")

    def fetch_fn(url):
        assert "matches.aspx" in url and tid in url
        return html

    archive_crawl.process_matches_tournament(conn, tid, fetch_fn, "now")

    draws = conn.execute("SELECT * FROM draws").fetchall()
    assert [d["id"] for d in draws] == ["AAAA1111-1111-1111-1111-111111111111:16"]
    assert draws[0]["name"] == "MS C"
    matches = conn.execute(
        "SELECT round_label, score_raw, winner_side FROM matches ORDER BY round_index"
    ).fetchall()
    labels = [m["round_label"] for m in matches]
    assert "Final" in labels and "Semi final" in labels
    final = next(m for m in matches if m["round_label"] == "Final")
    assert final["score_raw"] == "10-21 6-21"
    assert final["winner_side"] == 2
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

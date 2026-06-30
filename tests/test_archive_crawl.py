"""Tests for archive_fetch (Task 6) and archive crawl (Task 7+)."""

from badminton_tracker import archive_db, archive_fetch


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

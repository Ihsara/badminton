# tests/test_archive_endpoints.py
import importlib

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch, password="secret"):
    from badminton_tracker import config
    monkeypatch.setattr(config, "EDIT_PASSWORD", password)
    monkeypatch.setattr(config, "ARCHIVE_DB", tmp_path / "a.sqlite")
    from badminton_tracker import archive_db, server
    importlib.reload(server)  # pick up patched EDIT_PASSWORD in module-level refs
    conn = archive_db.connect(tmp_path / "a.sqlite")
    archive_db.upsert_tournament(conn, {
        "id": "T1", "name": "Cup 2024", "year": 2024, "start_date": "2024-04-12",
        "end_date": "2024-04-12", "location": None, "region": None,
        "category": None, "source_url": None, "fetched_at": "t"})
    conn.close()
    return TestClient(server.app)


def test_tournaments_requires_password(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.get("/api/archive/tournaments").status_code in (401, 403)


def test_tournaments_lists_with_password(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.get("/api/archive/tournaments", params={"password": "secret"})
    assert r.status_code == 200
    assert any(t["id"] == "T1" for t in r.json())

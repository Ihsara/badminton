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


def test_bracket_includes_player_names(tmp_path, monkeypatch):
    from badminton_tracker import archive_db

    c = _client(tmp_path, monkeypatch)
    conn = archive_db.connect(tmp_path / "a.sqlite")
    archive_db.upsert_draw(conn, {
        "id": "D1", "tournament_id": "T1", "name": "MS",
        "draw_type": "elimination", "ordering": 0})
    a = archive_db.upsert_player(conn, {
        "tournament_id": "T1", "display_name": "Alice Smith",
        "profile_guid": None, "club": None, "seed": None})
    b = archive_db.upsert_player(conn, {
        "tournament_id": "T1", "display_name": "Bob Jones",
        "profile_guid": None, "club": None, "seed": None})
    archive_db.insert_match(conn, {
        "draw_id": "D1", "round_label": "Final", "round_index": 0, "position": 0,
        "side1_player_ids": [a], "side2_player_ids": [b],
        "score_raw": "21-15 21-18", "winner_side": 1,
        "scheduled_iso": None, "court": None})
    conn.close()

    r = c.get("/api/archive/tournament/T1/bracket", params={"password": "secret"})
    assert r.status_code == 200
    m = r.json()["draws"][0]["matches"][0]
    assert [p["name"] for p in m["side1"]] == ["Alice Smith"]
    assert [p["name"] for p in m["side2"]] == ["Bob Jones"]


def test_core_names_requires_password(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.get("/api/archive/core-names").status_code in (401, 403)


def test_core_names_returns_core_set(tmp_path, monkeypatch):
    from badminton_tracker.core_group import CORE_NICKNAMES

    c = _client(tmp_path, monkeypatch)
    r = c.get("/api/archive/core-names", params={"password": "secret"})
    assert r.status_code == 200
    names = r.json()["names"]
    assert isinstance(names, list)
    assert "Chau" in names
    assert set(names) == set(CORE_NICKNAMES)

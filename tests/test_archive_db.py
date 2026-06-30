from badminton_tracker import archive_db, config


def test_archive_paths_live_under_private_data_dir():
    assert config.ARCHIVE_DIR == config.DATA_DIR / "archive"
    assert config.ARCHIVE_DB == config.ARCHIVE_DIR / "archive.sqlite"
    assert config.ARCHIVE_RAW_DIR == config.ARCHIVE_DIR / "raw"
    # Must be inside the private data repo, never the public web dir.
    assert config.DATA_DIR in config.ARCHIVE_DB.parents


def test_connect_creates_all_tables(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")
    names = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"tournaments", "draws", "players", "matches",
            "crawl_state", "raw_cache"} <= names
    conn.close()


def test_connect_enables_foreign_keys(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()


def test_upsert_player_is_idempotent(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")
    archive_db.upsert_tournament(conn, {
        "id": "T1", "name": "Cup", "year": 2024, "start_date": None,
        "end_date": None, "location": None, "region": None, "category": None,
        "source_url": None, "fetched_at": "2026-06-30"})
    p = {"tournament_id": "T1", "display_name": "Jane Doe",
         "profile_guid": "G1", "club": None, "seed": None}
    a = archive_db.upsert_player(conn, p)
    b = archive_db.upsert_player(conn, p)
    assert a == b
    n = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    assert n == 1
    conn.close()


def test_insert_match_stores_player_id_lists_as_json(tmp_path):
    import json
    conn = archive_db.connect(tmp_path / "a.sqlite")
    archive_db.upsert_tournament(conn, {
        "id": "T1", "name": "Cup", "year": 2024, "start_date": None,
        "end_date": None, "location": None, "region": None, "category": None,
        "source_url": None, "fetched_at": "x"})
    archive_db.upsert_draw(conn, {
        "id": "D1", "tournament_id": "T1", "name": "MD", "draw_type": "elimination",
        "ordering": 0})
    archive_db.insert_match(conn, {
        "draw_id": "D1", "round_label": "Final", "round_index": 0, "position": 0,
        "side1_player_ids": [1, 2], "side2_player_ids": [3, 4],
        "score_raw": "21-15 21-18", "winner_side": 1,
        "scheduled_iso": None, "court": None})
    row = conn.execute("SELECT side1_player_ids FROM matches").fetchone()
    assert json.loads(row[0]) == [1, 2]
    conn.close()


def test_upsert_player_null_guid_is_idempotent(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")
    archive_db.upsert_tournament(conn, {
        "id": "T1", "name": "Cup", "year": 2024, "start_date": None,
        "end_date": None, "location": None, "region": None, "category": None,
        "source_url": None, "fetched_at": "2026-06-30"})
    p = {"tournament_id": "T1", "display_name": "No Guid Player",
         "profile_guid": None, "club": None, "seed": None}
    a = archive_db.upsert_player(conn, p)
    b = archive_db.upsert_player(conn, p)
    c = archive_db.upsert_player(conn, p)
    assert a == b == c, f"Expected same id each time, got {a}, {b}, {c}"
    n = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    assert n == 1, f"Expected 1 row, got {n}"
    conn.close()


def test_set_state_and_pending(tmp_path):
    conn = archive_db.connect(tmp_path / "a.sqlite")
    for tid in ("T1", "T2"):
        archive_db.upsert_tournament(conn, {
            "id": tid, "name": tid, "year": 2024, "start_date": None,
            "end_date": None, "location": None, "region": None,
            "category": None, "source_url": None, "fetched_at": "x"})
    archive_db.set_state(conn, "T1", "pending", now="t")
    archive_db.set_state(conn, "T2", "done", now="t")
    assert archive_db.pending_tournaments(conn) == ["T1"]
    archive_db.set_state(conn, "T1", "error", error="boom", now="t")
    row = conn.execute(
        "SELECT attempts, last_error FROM crawl_state WHERE tournament_id='T1'"
    ).fetchone()
    assert row["attempts"] == 1 and row["last_error"] == "boom"
    conn.close()

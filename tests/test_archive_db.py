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

from badminton_tracker import config


def test_archive_paths_live_under_private_data_dir():
    assert config.ARCHIVE_DIR == config.DATA_DIR / "archive"
    assert config.ARCHIVE_DB == config.ARCHIVE_DIR / "archive.sqlite"
    assert config.ARCHIVE_RAW_DIR == config.ARCHIVE_DIR / "raw"
    # Must be inside the private data repo, never the public web dir.
    assert config.DATA_DIR in config.ARCHIVE_DB.parents

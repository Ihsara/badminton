from pathlib import Path

from badminton_tracker import config


def test_archive_store_is_under_private_data_dir_only():
    assert config.DATA_DIR in config.ARCHIVE_DB.parents
    assert config.DATA_DIR in config.ARCHIVE_RAW_DIR.parents
    web = (Path(config.__file__).resolve().parents[2] / "web")
    # Archive must NOT live under web/ (the publishable dir).
    assert web not in config.ARCHIVE_DB.parents
    assert web not in config.ARCHIVE_RAW_DIR.parents


def test_public_jsons_contain_no_profile_guids():
    root = Path(config.__file__).resolve().parents[2]
    guid = __import__("re").compile(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
    data = root / "web" / "data.json"
    if data.exists():
        # data.json must contain ZERO GUIDs (no tournament guids belong here).
        assert not guid.search(data.read_text(encoding="utf-8"))
    # upcoming.json MAY contain the tournament guid but is checked elsewhere;
    # here we only assert data.json stays GUID-free.


def test_no_archive_import_in_public_pipeline():
    src = Path(config.__file__).resolve().parent
    for mod in ("build.py", "export.py"):
        text = (src / mod).read_text(encoding="utf-8")
        assert "archive_db" not in text
        assert "archive_crawl" not in text
        assert "archive_fetch" not in text

from pathlib import Path

from badminton_tracker.exclude import load_excludes


def test_loads_names_lowercased(tmp_path: Path):
    p = tmp_path / "exclude.csv"
    p.write_text("name,reason\nYuki Matti,x\nToni Seppälä,y\n", encoding="utf-8")
    assert load_excludes(p) == {"yuki matti", "toni seppälä"}


def test_missing_file_is_empty(tmp_path: Path):
    assert load_excludes(tmp_path / "nope.csv") == set()

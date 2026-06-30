from pathlib import Path

from badminton_tracker import archive_enumerate

FIX = Path(__file__).parent / "fixtures" / "archive" / "find_tournament_page.html"


def test_parse_tournament_list_dedupes_and_extracts_dates():
    html = FIX.read_text(encoding="utf-8")
    out = archive_enumerate.parse_tournament_list(html)
    ids = [t["id"].lower() for t in out]
    assert ids.count("11111111-1111-1111-1111-111111111111") == 1  # de-duped
    by_id = {t["id"].lower(): t for t in out}
    assert by_id["11111111-1111-1111-1111-111111111111"]["start_date"] == "2024-04-12"
    assert by_id["22222222-2222-2222-2222-222222222222"]["start_date"] == "2022-10-03"


def test_parse_tournament_list_skips_registration_links():
    html = FIX.read_text(encoding="utf-8")
    names = [t["name"].lower() for t in archive_enumerate.parse_tournament_list(html)]
    assert not any("ilmoittautu" in n for n in names)

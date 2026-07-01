from pathlib import Path

from badminton_tracker import archive_profile

FIX = Path(__file__).parent / "fixtures" / "archive"


def test_parse_profile_tournaments_finds_finished_deduped_skips_header():
    html = (FIX / "profile_history.html").read_text(encoding="utf-8")
    tours = archive_profile.parse_profile_tournaments(html)
    ids = [t["id"] for t in tours]
    # profile-header card (player.aspx only) is skipped; each tournament found once
    # first-seen order: BBBB card, then the DDDD real-DOM card, then CCCC card
    assert ids == ["BBBB2222-2222-2222-2222-222222222222",
                   "DDDD4444-4444-4444-4444-444444444444",
                   "CCCC3333-3333-3333-3333-333333333333"]
    assert tours[0]["name"] == "Spring Open 2025"
    assert tours[0]["start_date"] is None


def test_parse_profile_tournaments_name_from_titled_anchor_not_empty_img_anchor():
    """Real DOM: an image anchor (no text) precedes the titled name anchor for the
    same tournament. The name must come from the titled anchor, never be empty."""
    html = (FIX / "profile_history.html").read_text(encoding="utf-8")
    tours = archive_profile.parse_profile_tournaments(html)
    dddd = next(t for t in tours if t["id"] == "DDDD4444-4444-4444-4444-444444444444")
    assert dddd["name"] == "Autumn Slam 2023"


def test_parse_profile_tournaments_tolerates_trailing_query_params():
    html = (
        '<a href="/sport/tournament?id=DDDD4444-4444-4444-4444-444444444444'
        '&amp;draw=1">Autumn Slam 2023</a>'
    )
    tours = archive_profile.parse_profile_tournaments(html)
    ids = [t["id"] for t in tours]
    assert ids == ["DDDD4444-4444-4444-4444-444444444444"]
    assert tours[0]["name"] == "Autumn Slam 2023"

from badminton_tracker.upcoming_find import find_upcoming_tournaments

HTML = """
<a href="/sport/tournament?id=1A563200-14BA-4328-955A-922A5EEC6374">Stadin Sulan kesäkisat 4.7.2026</a>
<a href="/onlineentry/onlineentry.aspx?id=1A563200-14BA-4328-955A-922A5EEC6374">ILMOITTAUTUMINEN</a>
<a href="/sport/tournament?id=5C87C899-38D1-42CA-8049-4CE32CD5A2B5">Kaarinan Heinäturnaus 2026</a>
<a href="/sport/tournament?id=1A563200-14BA-4328-955A-922A5EEC6374">Stadin Sulan kesäkisat 4.7.2026</a>
"""


def test_extracts_unique_tournaments_skipping_entry_links():
    out = find_upcoming_tournaments(HTML, "2026-06-28", horizon_days=60)
    guids = [t["guid"] for t in out]
    assert "1A563200-14BA-4328-955A-922A5EEC6374" in guids
    assert guids.count("1A563200-14BA-4328-955A-922A5EEC6374") == 1  # de-duped
    assert all("ilmoittautu" not in t["name"].lower() for t in out)


def test_parses_finnish_date_from_name():
    out = find_upcoming_tournaments(HTML, "2026-06-28", horizon_days=60)
    stadin = next(t for t in out if t["guid"].startswith("1A563200"))
    assert stadin["start_date"] == "2026-07-04"

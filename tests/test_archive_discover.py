from badminton_tracker import archive_discover


def test_discover_unions_tournaments_across_profiles_dedup():
    pages = {
        "http://b/player-profile/g1":
            '<a href="/sport/tournament?id=BBBB2222-2222-2222-2222-222222222222">A 2025</a>',
        "http://b/player-profile/g2":
            '<a href="/sport/tournament?id=BBBB2222-2222-2222-2222-222222222222">A 2025</a>'
            '<a href="/sport/tournament?id=CCCC3333-3333-3333-3333-333333333333">B 2024</a>',
    }
    calls = []

    def fetch_fn(url):
        calls.append(url)
        return pages[url]

    out = archive_discover.discover_tournament_ids(fetch_fn, ["g1", "g2"], "http://b")
    ids = [t["id"] for t in out]
    assert ids == ["BBBB2222-2222-2222-2222-222222222222",
                   "CCCC3333-3333-3333-3333-333333333333"]
    assert calls == ["http://b/player-profile/g1", "http://b/player-profile/g2"]

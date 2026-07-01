from badminton_tracker import archive_db
from tests.fixtures.archive.seed_demo import seed_demo


def test_seed_demo_builds_multiround_bracket(tmp_path):
    db = tmp_path / "demo.sqlite"
    tid = seed_demo(db)
    conn = archive_db.connect(db)
    rounds = {r["round_index"] for r in conn.execute(
        "SELECT m.round_index FROM matches m "
        "JOIN draws d ON d.id=m.draw_id WHERE d.tournament_id=?", (tid,)).fetchall()}
    conn.close()
    assert {0, 1, 2} <= rounds  # Final, Semi, Quarter present

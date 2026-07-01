"""Dev/test seeder: one elimination draw with Quarter→Semi→Final, real-shaped
(names, winners, scores) so the bracket view has something to render. NOT prod."""
from __future__ import annotations

from pathlib import Path

from badminton_tracker import archive_db


def seed_demo(db_path: Path) -> str:
    conn = archive_db.connect(db_path)
    tid = "DEMO-T1"
    archive_db.upsert_tournament(conn, {
        "id": tid, "name": "Demo Open 2024", "year": 2024,
        "start_date": "2024-04-12", "end_date": "2024-04-13", "location": "Helsinki",
        "region": None, "category": None, "source_url": None, "fetched_at": "t"})
    archive_db.upsert_draw(conn, {
        "id": "D1", "tournament_id": tid, "name": "Men's Singles",
        "draw_type": "elimination", "ordering": 0})
    names = ["Alice Smith", "Bob Jones", "Cara Lee", "Dan Park",
             "Eve Kahn", "Finn Oja", "Gia Roy", "Hugo Vik"]
    pid = {n: archive_db.upsert_player(conn, {
        "tournament_id": tid, "display_name": n, "profile_guid": None,
        "club": None, "seed": None}) for n in names}

    def match(round_index, round_label, position, s1, s2, winner, score):
        archive_db.insert_match(conn, {
            "draw_id": "D1", "round_label": round_label, "round_index": round_index,
            "position": position, "side1_player_ids": [pid[s1]],
            "side2_player_ids": [pid[s2]], "score_raw": score,
            "winner_side": winner, "scheduled_iso": None, "court": None})

    # Quarter finals (round_index 2)
    match(2, "Quarter final", 0, "Alice Smith", "Bob Jones", 1, "21-15 21-18")
    match(2, "Quarter final", 1, "Cara Lee", "Dan Park", 2, "19-21 21-17 21-12")
    match(2, "Quarter final", 2, "Eve Kahn", "Finn Oja", 1, "21-9 21-14")
    match(2, "Quarter final", 3, "Gia Roy", "Hugo Vik", 2, "21-19 21-19")
    # Semi finals (round_index 1)
    match(1, "Semi final", 0, "Alice Smith", "Dan Park", 1, "21-16 21-13")
    match(1, "Semi final", 1, "Eve Kahn", "Hugo Vik", 2, "18-21 21-15 21-19")
    # Final (round_index 0)
    match(0, "Final", 0, "Alice Smith", "Hugo Vik", 1, "21-17 21-15")
    conn.commit()
    conn.close()
    return tid

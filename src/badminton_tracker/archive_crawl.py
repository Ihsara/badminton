"""Resumable crawl state machine.

Ties enumerate→fetch→parse→store together, checkpointing each tournament in
crawl_state so an interrupted multi-day run resumes cleanly.  The fetch
function is injected (Playwright live, fake in tests).
"""

from __future__ import annotations

from . import archive_db, archive_parse
from .config import BASE_URL


def _year_of(start_date: str | None) -> int | None:
    return int(start_date[:4]) if start_date else None


def _draws_url(tid: str) -> str:
    return f"{BASE_URL}/sport/draws.aspx?id={tid}"


def _bracket_url(draw_href: str) -> str:
    if draw_href.startswith("http"):
        return draw_href
    if draw_href.startswith("/"):
        return f"{BASE_URL}{draw_href}"
    return f"{BASE_URL}/{draw_href}"


def process_tournament(conn, tid: str, fetch_fn, now: str) -> None:
    """Fetch, parse, and store all draws + matches for one tournament.

    Raises on any fetch/parse/DB error — the caller (run) catches and records
    the error in crawl_state without crashing the loop.
    """
    draws_html = fetch_fn(_draws_url(tid))
    draws = archive_parse.parse_draw_list(draws_html)
    for d in draws:
        draw_id = d["id"]
        archive_db.upsert_draw(conn, {
            "id": draw_id,
            "tournament_id": tid,
            "name": d["name"],
            "draw_type": d["draw_type"],
            "ordering": d["ordering"],
        })
        bracket_html = fetch_fn(_bracket_url(draw_id))
        for m in archive_parse.parse_bracket(bracket_html):
            sides = m["sides"]
            side1_ids: list[int] = []
            side2_ids: list[int] = []
            if len(sides) > 0:
                for pl in sides[0]:
                    pid = archive_db.upsert_player(conn, {
                        "tournament_id": tid,
                        "display_name": pl["name"],
                        "profile_guid": pl.get("profile_guid"),
                        "club": None,
                        "seed": pl.get("seed"),
                    })
                    side1_ids.append(pid)
            if len(sides) > 1:
                for pl in sides[1]:
                    pid = archive_db.upsert_player(conn, {
                        "tournament_id": tid,
                        "display_name": pl["name"],
                        "profile_guid": pl.get("profile_guid"),
                        "club": None,
                        "seed": pl.get("seed"),
                    })
                    side2_ids.append(pid)
            archive_db.insert_match(conn, {
                "draw_id": draw_id,
                "round_label": m["round_label"],
                "round_index": m["round_index"],
                "position": m["position"],
                "side1_player_ids": side1_ids,
                "side2_player_ids": side2_ids,
                "score_raw": m["score_raw"],
                "winner_side": m["winner_side"],
                "scheduled_iso": m["scheduled_iso"],
                "court": m["court"],
            })


def run(
    conn,
    tournament_ids: list[dict],
    fetch_fn,
    now: str,
) -> dict:
    """Upsert tournaments + seed pending state, then process every non-done one.

    Idempotent: tournaments already marked 'done' are skipped.  Errors are
    recorded per tournament; the loop always continues.

    Returns {"done": n, "error": m}.
    """
    for t in tournament_ids:
        archive_db.upsert_tournament(conn, {
            "id": t["id"],
            "name": t.get("name"),
            "year": _year_of(t.get("start_date")),
            "start_date": t.get("start_date"),
            "end_date": t.get("end_date", t.get("start_date")),
            "location": None,
            "region": None,
            "category": None,
            "source_url": f"{BASE_URL}/sport/tournament?id={t['id']}",
            "fetched_at": now,
        })
        existing = conn.execute(
            "SELECT status FROM crawl_state WHERE tournament_id=?", (t["id"],)
        ).fetchone()
        if existing is None:
            archive_db.set_state(conn, t["id"], "pending", now=now)

    done = err = 0
    for tid in archive_db.pending_tournaments(conn):
        try:
            process_tournament(conn, tid, fetch_fn, now)
            archive_db.set_state(conn, tid, "done", now=now)
            done += 1
        except Exception as e:  # noqa: BLE001 — record + continue, never crash the crawl
            archive_db.set_state(conn, tid, "error", error=str(e), now=now)
            err += 1
    return {"done": done, "error": err}

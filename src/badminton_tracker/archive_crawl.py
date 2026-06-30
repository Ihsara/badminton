"""Resumable crawl state machine.

Ties enumerate->fetch->parse->store together, checkpointing each tournament in
crawl_state so an interrupted multi-day run resumes cleanly.  The fetch
function is injected (Playwright live, fake in tests).
"""

from __future__ import annotations

from datetime import datetime

from . import archive_db, archive_parse
from .config import BASE_URL


def _now_str(now: str | datetime) -> str:
    """Coerce now to an ISO-8601 string so callers may pass either form."""
    if isinstance(now, datetime):
        return now.isoformat()
    return now


def crawl_live(  # pragma: no cover
    *,
    year_from: int = 2020,
    year_to: int = 2026,
    refresh_months: int | None = None,
    delay_ms: int = 700,
    max_pages: int = 40,
) -> dict:
    """Drive a live Playwright session to crawl all reachable tournaments into the archive.

    NOTE (confirmed against the live site 2026-06-30): /find/tournament IGNORES
    the YearNr/date params and only returns the CURRENT upcoming window (~14
    tournaments), so this year-range enumeration does NOT reach finished
    historical (2020-2025) tournaments -- see the existing upcoming_find.py
    docstring. Reaching historical tournaments needs a different discovery path
    (e.g. /tournament/{guid}/players scans), which is a documented follow-up.
    This driver is wired and correct for the enumeration the site exposes; it is
    intentionally NOT exercised by a live run in this branch.
    """
    # refresh_months: reserved for sub-project C (cache-freshness top-up); not yet wired.
    import datetime as dt

    from playwright.sync_api import sync_playwright

    from . import archive_enumerate, archive_fetch, client

    now = dt.datetime.now(dt.UTC).isoformat()
    conn = archive_db.connect()
    p = sync_playwright().start()
    browser, ctx = client.new_context(p, headless=True)
    try:
        page = client.ensure_login(ctx)

        def getter(url: str) -> tuple[str, int]:
            page.goto(url, wait_until="domcontentloaded")
            client.dismiss_cookies(page)
            page.wait_for_timeout(300)
            return page.content(), 200

        def fetch_fn(url: str) -> str:
            return archive_fetch.fetch(conn, url, getter, now, delay_ms=delay_ms)

        tournaments: dict[str, dict] = {}
        for year in range(year_from, year_to + 1):
            for page_num in range(1, max_pages + 1):
                url = (
                    f"{BASE_URL}/find/tournament"
                    f"?YearNr={year}&p={page_num}"
                )
                html = fetch_fn(url)
                items = archive_enumerate.parse_tournament_list(html)
                if not items:
                    break
                for t in items:
                    key = t["id"].lower()
                    if key not in tournaments:
                        tournaments[key] = t

        return run(conn, list(tournaments.values()), fetch_fn, now)
    finally:
        ctx.close()
        browser.close()
        p.stop()
        conn.close()


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


def process_tournament(conn, tid: str, fetch_fn, now: str | datetime) -> None:
    """Fetch, parse, and store all draws + matches for one tournament.

    Raises on any fetch/parse/DB error -- the caller (run) catches and records
    the error in crawl_state without crashing the loop.
    """
    now = _now_str(now)  # normalise datetime -> str once at the top
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
    now: str | datetime,
) -> dict:
    """Upsert tournaments + seed pending state, then process every non-done one.

    Idempotent: tournaments already marked done are skipped.  Errors are
    recorded per tournament; the loop always continues.

    Returns {"done": n, "error": m}.
    """
    now = _now_str(now)  # normalise datetime -> str once at the top
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
        except Exception as e:  # noqa: BLE001 -- record + continue, never crash the crawl
            archive_db.set_state(conn, tid, "error", error=str(e), now=now)
            err += 1
    return {"done": done, "error": err}

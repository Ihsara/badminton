"""Always-on web server: explorer + maintainer endpoints.

Runs in the local Windows container. Serves the static explorer and exposes a
small, password-protected API so Santeri can replace the Excel and friends can
edit nicknames from the browser. Every successful write is validated in Python
and committed to the private data repo (full, revertable history).

Read endpoints are open; write endpoints require the shared edit password.
"""

from __future__ import annotations

import hmac
import json

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import aliases, versioning
from .build import write_matches_mirror
from .config import ARCHIVE_DB, EDIT_PASSWORD, MAX_UPLOAD_BYTES, SOURCE_XLSX
from .export import WEB_DIR, export_from_excel
from .validate import ValidationError, validate_alias_rows, validate_workbook_bytes

app = FastAPI(title="Badminton Bros", docs_url=None, redoc_url=None)

# The public site may drive this container when it is exposed over HTTPS (e.g.
# via a tunnel): GET for live data/health, POST for edits. Writes stay safe —
# every POST is gated by the shared edit password, not by origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _writes_enabled() -> bool:
    return bool(EDIT_PASSWORD)


def _check_password(supplied: str | None) -> None:
    if not _writes_enabled():
        raise HTTPException(403, "Editing is disabled on this server (no edit password set).")
    if not supplied or not hmac.compare_digest(str(supplied), EDIT_PASSWORD):
        raise HTTPException(401, "Wrong edit password.")


def _data_counts() -> dict:
    f = WEB_DIR / "data.json"
    if not f.exists():
        return {}
    try:
        payload = json.loads(f.read_text(encoding="utf-8"))
        return {"counts": payload.get("counts", {}), "generated_at": payload.get("generated_at")}
    except (OSError, ValueError):
        return {}


@app.exception_handler(ValidationError)
async def _on_validation_error(_: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"ok": False, "errors": exc.messages})


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "badminton-bros",
        "writes_enabled": _writes_enabled(),
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        **_data_counts(),
    }


@app.get("/api/nicknames")
def get_nicknames() -> dict:
    return {"ok": True, "rows": aliases.load_aliases(), "writes_enabled": _writes_enabled()}


@app.post("/api/nicknames")
async def post_nicknames(request: Request) -> dict:
    body = await request.json()
    _check_password(body.get("password"))
    rows = validate_alias_rows(body.get("rows", []))
    aliases.write_aliases(rows)
    export_from_excel()  # re-render data.json with the new nicknames
    commit = versioning.commit(
        ["aliases.csv"], "Edit nicknames via web", who=body.get("who")
    )
    return {
        "ok": True,
        "committed": commit,
        "rows": len(rows),
        "history": versioning.history("aliases.csv", limit=5),
        **_data_counts(),
    }


@app.post("/api/upload-excel")
async def upload_excel(
    file: UploadFile = File(...),
    password: str = Form(...),
    who: str = Form(""),
) -> dict:
    _check_password(password)
    raw = await file.read()
    summary = validate_workbook_bytes(raw)  # raises ValidationError on bad input

    SOURCE_XLSX.write_bytes(raw)
    write_matches_mirror()  # readable CSV delta beside the binary workbook
    export_from_excel()  # refresh the live explorer data

    commit = versioning.commit(
        [SOURCE_XLSX.name, "matches_mirror.csv", "aliases.csv"],
        f"Update match log via web ({summary['matches']} matches)",
        who=who,
    )
    return {
        "ok": True,
        "committed": commit,
        "matches": summary["matches"],
        "diff": versioning.last_diff("matches_mirror.csv")[:20_000],
        "history": versioning.history("matches_mirror.csv", limit=5),
        **_data_counts(),
    }


@app.get("/api/archive/tournaments")
def archive_tournaments(password: str | None = None):
    _check_password(password)
    from . import archive_db
    if not ARCHIVE_DB.exists():
        return []
    conn = archive_db.connect(ARCHIVE_DB)
    try:
        rows = conn.execute(
            "SELECT id,name,year,start_date FROM tournaments ORDER BY year DESC, name"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/archive/tournament/{tid}/bracket")
def archive_bracket(tid: str, password: str | None = None):
    _check_password(password)
    from . import archive_db
    if not ARCHIVE_DB.exists():
        raise HTTPException(404, "Archive not built")
    conn = archive_db.connect(ARCHIVE_DB)
    try:
        t = conn.execute("SELECT * FROM tournaments WHERE id=?", (tid,)).fetchone()
        if t is None:
            raise HTTPException(404, "Unknown tournament")
        players = {r["id"]: r["display_name"] for r in conn.execute(
            "SELECT id, display_name FROM players WHERE tournament_id=?", (tid,)
        ).fetchall()}

        def _side(raw):
            ids = json.loads(raw) if raw else []
            return [{"id": pid, "name": players.get(pid, "?")} for pid in ids]

        draws = []
        for d in conn.execute(
            "SELECT * FROM draws WHERE tournament_id=? ORDER BY ordering", (tid,)
        ).fetchall():
            matches = []
            for m in conn.execute(
                "SELECT * FROM matches WHERE draw_id=? ORDER BY round_index, position",
                (d["id"],)).fetchall():
                md = dict(m)
                md["side1"] = _side(md["side1_player_ids"])
                md["side2"] = _side(md["side2_player_ids"])
                matches.append(md)
            draws.append({**dict(d), "matches": matches})
        return {"tournament": dict(t), "draws": draws}
    finally:
        conn.close()


# Static explorer LAST so /api/* wins. html=True serves index.html at "/".
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    if not (WEB_DIR / "data.json").exists():
        print("web/data.json missing — generating from the workbook…")
        export_from_excel()
    print(f"Badminton Bros server →  http://localhost:{port}")
    state = "ENABLED" if _writes_enabled() else "disabled (set BADMINTON_EDIT_PASSWORD)"
    print(f"  writes {state}")
    uvicorn.run(app, host=host, port=port)

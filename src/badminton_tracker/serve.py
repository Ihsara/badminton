"""Serve the static explorer in web/ over HTTP (needed for fetch of data.json)."""

from __future__ import annotations

import http.server
import socketserver
from functools import partial

from .export import WEB_DIR


def serve(port: int = 8000) -> None:
    if not (WEB_DIR / "data.json").exists():
        print("web/data.json missing — run `uv run badminton export` (or `build`) first.")
        return
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(WEB_DIR))
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Explorer live →  http://localhost:{port}")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")

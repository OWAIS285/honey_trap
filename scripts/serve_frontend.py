"""Serve frontend/public on http://localhost:5000 with caching disabled (local testing only)."""

import functools
import http.server
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "public"


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    handler = functools.partial(NoCacheHandler, directory=str(ROOT))
    with http.server.ThreadingHTTPServer(("127.0.0.1", 5000), handler) as server:
        print("Serving", ROOT, "on http://localhost:5000")
        server.serve_forever()

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from cardhunt import __version__
from cardhunt.engine import hunt, listings, status_payload
from cardhunt.settings import get_settings

STATIC = Path(__file__).resolve().parent / "static"


def _json(handler: BaseHTTPRequestHandler, code: int, payload: object) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _html(handler: BaseHTTPRequestHandler, path: Path) -> None:
    data = path.read_bytes()
    ctype = "text/html; charset=utf-8"
    if path.suffix == ".css":
        ctype = "text/css; charset=utf-8"
    elif path.suffix == ".js":
        ctype = "application/javascript; charset=utf-8"
    elif path.suffix == ".svg":
        ctype = "image/svg+xml"
    handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class HuntHandler(BaseHTTPRequestHandler):
    server_version = f"CardHunt/{__version__}"

    def log_message(self, fmt: str, *args) -> None:
        # Quieter logs on phone terminals.
        sys_stderr = __import__("sys").stderr
        sys_stderr.write("cardhunt: " + (fmt % args) + "\n")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/", "/index.html"}:
            return _html(self, STATIC / "index.html")
        if path.startswith("/static/"):
            rel = path.removeprefix("/static/")
            target = (STATIC / rel).resolve()
            if not str(target).startswith(str(STATIC.resolve())) or not target.exists():
                self.send_error(404)
                return
            return _html(self, target)
        if path == "/api/status":
            return _json(self, 200, status_payload())
        if path == "/api/listings":
            qs = parse_qs(parsed.query)
            steals = (qs.get("steals") or ["0"])[0] in {"1", "true", "yes"}
            return _json(self, 200, {"items": listings(steals_only=steals)})
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return _json(self, 400, {"error": "invalid json"})

        if parsed.path == "/api/hunt":
            query = str(payload.get("query") or "").strip() or None
            demo = bool(payload.get("demo"))
            sites = payload.get("sites")
            if isinstance(sites, str):
                sites = [s.strip() for s in sites.split(",") if s.strip()]
            limit = payload.get("limit")
            try:
                result = hunt(
                    query=query,
                    sites=sites if isinstance(sites, list) else None,
                    limit=int(limit) if limit is not None else None,
                    demo=demo,
                    skip_vision=bool(payload.get("skip_vision") or demo),
                )
                items = listings(steals_only=False)
                steals = listings(steals_only=True)
                return _json(
                    self,
                    200,
                    {
                        "ok": True,
                        "stats": result,
                        "items": items[:80],
                        "steals": steals[:40],
                    },
                )
            except Exception as exc:  # noqa: BLE001
                return _json(self, 500, {"ok": False, "error": str(exc)})

        self.send_error(404)


def serve(host: str | None = None, port: int | None = None) -> None:
    settings = get_settings()
    host = host or settings.host
    port = port or settings.port
    httpd = ThreadingHTTPServer((host, port), HuntHandler)
    print(f"CardHunt phone UI → http://{host}:{port}/")
    print("On your phone (same Wi‑Fi): open http://<this-computer-ip>:" + str(port) + "/")
    print("Demo works with no API keys. Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()

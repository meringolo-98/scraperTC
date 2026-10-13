from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from threading import Thread

import pytest

from cardhunt.engine import hunt, status_payload
from cardhunt.server import HuntHandler
from cardhunt.settings import clear_caches


@pytest.fixture(autouse=True)
def _clear(tmp_path, monkeypatch):
    monkeypatch.setenv("CARDHUNT_DB", str(tmp_path / "cardhunt.db"))
    monkeypatch.setenv("SCRAPERTC_CARDS_DB", str(tmp_path / "cards.db"))
    clear_caches()
    from scrapertc.settings import get_settings

    get_settings.cache_clear()
    yield
    clear_caches()
    get_settings.cache_clear()


def test_status_demo_ready():
    payload = status_payload()
    assert payload["product"] == "CardHunt"
    assert payload["demo_ready"] is True


def test_demo_hunt_finds_steal():
    result = hunt(query="Charizard Base 4/102", demo=True, skip_vision=True)
    assert result["collect"]["upserted"] >= 4  # type: ignore[index]
    assert result["steals"]["candidates"] >= 1  # type: ignore[index]


def test_phone_api_hunt_demo(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), HuntHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        import urllib.request

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/hunt",
            data=json.dumps({"demo": True, "query": "Charizard"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        assert data["ok"] is True
        assert len(data["items"]) >= 4
        assert len(data["steals"]) >= 1

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as resp:
            html = resp.read().decode()
        assert "CardHunt" in html
        assert "Hunt" in html
    finally:
        server.shutdown()

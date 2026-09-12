from __future__ import annotations

import time
from typing import Any

import httpx

from scrapertc.settings import Settings


class Http:
    def __init__(self, settings: Settings):
        headers = {"User-Agent": settings.user_agent, "Accept": "application/json"}
        if settings.contact_email:
            headers["From"] = settings.contact_email
        self.settings = settings
        self._client = httpx.Client(timeout=30.0, headers=headers, follow_redirects=True)
        self._last_request = 0.0

    def close(self) -> None:
        self._client.close()

    def _pace(self) -> None:
        wait = self.settings.request_delay_seconds
        elapsed = time.monotonic() - self._last_request
        if elapsed < wait:
            time.sleep(wait - elapsed)
        self._last_request = time.monotonic()

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        auth: httpx.Auth | tuple[str, str] | None = None,
    ) -> httpx.Response:
        last: httpx.Response | None = None
        for attempt in range(3):
            self._pace()
            try:
                last = self._client.get(url, params=params, headers=headers, auth=auth)
            except httpx.TransportError:
                if attempt == 2:
                    raise
                time.sleep(1.5 * (attempt + 1))
                continue
            if last.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            return last
        assert last is not None
        return last

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        auth: httpx.Auth | tuple[str, str] | None = None,
        ok_statuses: set[int] | None = None,
    ) -> Any | None:
        response = self.get(url, params=params, headers=headers, auth=auth)
        allowed = ok_statuses or {200}
        if response.status_code not in allowed:
            return None
        if not response.content:
            return None
        return response.json()

    def get_text(self, url: str, *, params: dict[str, Any] | None = None) -> str | None:
        response = self.get(url, params=params)
        if response.status_code != 200:
            return None
        return response.text

    def post(
        self,
        url: str,
        *,
        data: dict[str, Any] | None = None,
        auth: httpx.Auth | tuple[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        self._pace()
        return self._client.post(url, data=data, auth=auth, headers=headers)

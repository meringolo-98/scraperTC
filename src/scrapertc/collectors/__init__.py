from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from scrapertc.http import Http
from scrapertc.models import ChatterItem, make_item_id, squeeze
from scrapertc.settings import Settings, sources_config

CollectorFn = Callable[[Http, Settings, int], list[ChatterItem]]


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, (int, float)):
        # seconds vs milliseconds
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=UTC)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def item(
    *,
    source: str,
    url: str,
    title: str,
    body: str = "",
    author: str | None = None,
    published_at: Any = None,
    query: str = "",
    extra: dict[str, Any] | None = None,
) -> ChatterItem:
    url = squeeze(url)
    return ChatterItem(
        id=make_item_id(source, url, fallback=f"{title}|{body[:80]}"),
        source=source,
        url=url,
        title=squeeze(title),
        body=squeeze(body),
        author=squeeze(author) or None,
        published_at=parse_datetime(published_at),
        query=query,
        extra=extra or {},
    )


def enabled(name: str) -> bool:
    collectors = (sources_config().get("collectors") or {}).get(name) or {}
    return bool(collectors.get("enabled", True))


def collector_conf(name: str) -> dict[str, Any]:
    return dict((sources_config().get("collectors") or {}).get(name) or {})

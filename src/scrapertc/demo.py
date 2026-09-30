from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from scrapertc.collectors import item
from scrapertc.models import ChatterItem

ASSETS = Path(__file__).resolve().parent / "assets" / "demo_chatter.json"


@lru_cache(maxsize=1)
def demo_items() -> list[ChatterItem]:
    payload = json.loads(ASSETS.read_text(encoding="utf-8"))
    items: list[ChatterItem] = []
    for row in payload:
        items.append(
            item(
                source=row["source"],
                url=row["url"],
                title=row["title"],
                body=row.get("body") or "",
                author=row.get("author"),
                published_at=row.get("published_at"),
                query=row.get("query") or "demo",
                extra=row.get("extra") or {},
            )
        )
    return items

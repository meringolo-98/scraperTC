from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from scrapertc.cards.collectors import listing
from scrapertc.cards.models import CardListing

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "demo_cards.json"


@lru_cache(maxsize=1)
def demo_card_listings() -> list[CardListing]:
    rows = json.loads(ASSETS.read_text(encoding="utf-8"))
    items: list[CardListing] = []
    for row in rows:
        items.append(
            listing(
                source=str(row.get("source") or "demo"),
                url=str(row.get("url") or ""),
                title=str(row.get("title") or ""),
                body=str(row.get("body") or ""),
                price_usd=row.get("price_usd"),
                image_urls=list(row.get("image_urls") or []),
                seller=row.get("seller"),
                condition=row.get("condition"),
                query=str(row.get("query") or "demo"),
                extra=dict(row.get("extra") or {}),
            )
        )
    return items

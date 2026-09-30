from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scrapertc.cards.catalog import infer_condition
from scrapertc.cards.config import (
    build_queries,
    collector_conf,
    collector_enabled,
    enabled_sites,
)
from scrapertc.cards.models import CardListing, make_listing_id, parse_price_usd
from scrapertc.http import Http
from scrapertc.models import squeeze
from scrapertc.settings import Settings


def listing(
    *,
    source: str,
    url: str,
    title: str,
    body: str = "",
    price_usd: float | None = None,
    image_urls: list[str] | None = None,
    seller: str | None = None,
    condition: str | None = None,
    query: str = "",
    extra: dict[str, Any] | None = None,
) -> CardListing:
    text = f"{title} {body}"
    return CardListing(
        id=make_listing_id(source, url, fallback=f"{title}|{body[:80]}"),
        source=source,
        url=squeeze(url),
        title=squeeze(title),
        body=squeeze(body),
        price_usd=price_usd if price_usd is not None else parse_price_usd(text),
        image_urls=image_urls or [],
        seller=squeeze(seller) or None,
        condition=condition or infer_condition(text),
        query=query,
        extra=extra or {},
    )


def _dedupe(items: list[CardListing]) -> list[CardListing]:
    seen: set[str] = set()
    unique: list[CardListing] = []
    for entry in items:
        if entry.id in seen:
            continue
        seen.add(entry.id)
        unique.append(entry)
    return unique


def collect_brave_markets(
    http: Http,
    settings: Settings,
    limit: int,
    *,
    query: str | None = None,
    sites: list[str] | None = None,
) -> list[CardListing]:
    """Marketplace discovery via Brave site: scopes — same path as Gate 1 web net."""
    if not collector_enabled("brave_markets"):
        return []
    if not settings.brave_api_key:
        return []
    wanted = enabled_sites()
    if sites:
        wanted = {name: conf for name, conf in wanted.items() if name in sites}
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": settings.brave_api_key,
    }
    items: list[CardListing] = []
    for q in build_queries(query)[: max(1, min(8, limit))]:
        for site_name, conf in wanted.items():
            scope = str(conf.get("scope") or "").strip()
            suffix = str(conf.get("query_suffix") or "").strip()
            full_q = " ".join(p for p in (q, suffix, scope) if p)
            data = http.get_json(
                "https://api.search.brave.com/res/v1/web/search",
                params={
                    "q": full_q,
                    "count": min(20, max(limit, 5)),
                    "offset": 0,
                    "country": "us",
                    "search_lang": "en",
                },
                headers=headers,
            )
            if not isinstance(data, dict):
                continue
            for row in (data.get("web") or {}).get("results") or []:
                url = row.get("url") or ""
                title = row.get("title") or ""
                if not url or not title:
                    continue
                thumb = row.get("thumbnail") or {}
                image = thumb.get("src") if isinstance(thumb, dict) else None
                items.append(
                    listing(
                        source=site_name,
                        url=url,
                        title=title,
                        body=row.get("description") or "",
                        image_urls=[image] if image else [],
                        query=full_q,
                        extra={"engine": "brave", "site": site_name},
                    )
                )
    return _dedupe(items)[: limit * max(1, len(wanted))]


def collect_pokemontcg(
    http: Http,
    settings: Settings,
    limit: int,
    *,
    query: str | None = None,
) -> list[CardListing]:
    """Official Pokemon TCG API — catalog + market prices (public)."""
    if not collector_enabled("pokemontcg"):
        return []
    items: list[CardListing] = []
    headers = {"Accept": "application/json"}
    api_key = getattr(settings, "pokemontcg_api_key", "") or ""
    if api_key:
        headers["X-Api-Key"] = api_key
    for q in build_queries(query)[: max(1, min(6, limit))]:
        # Prefer structured q= when we can; fall back to free text.
        api_q = _pokemontcg_query(q)
        data = http.get_json(
            "https://api.pokemontcg.io/v2/cards",
            params={"q": api_q, "pageSize": min(20, limit)},
            headers=headers,
        )
        if not isinstance(data, dict):
            continue
        for row in data.get("data") or []:
            card_id = row.get("id") or ""
            name = row.get("name") or ""
            if not card_id or not name:
                continue
            set_info = row.get("set") or {}
            number = row.get("number") or ""
            set_name = set_info.get("name") or ""
            images = row.get("images") or {}
            image_urls = [u for u in (images.get("large"), images.get("small")) if u]
            prices = _extract_tcgplayer_prices(row)
            price = prices.get("market") or prices.get("mid") or prices.get("low")
            title = f"{name} — {set_name} #{number}".strip(" —")
            body_parts = [
                f"rarity={row.get('rarity') or 'unknown'}",
                f"artist={row.get('artist') or 'unknown'}",
            ]
            if prices:
                body_parts.append(
                    "tcgplayer "
                    + ", ".join(f"{k}=${v:.2f}" for k, v in prices.items() if v is not None)
                )
            items.append(
                listing(
                    source="pokemontcg",
                    url=f"https://www.pokemontcg.io/card/{card_id}",
                    title=title,
                    body="; ".join(body_parts),
                    price_usd=price,
                    image_urls=image_urls,
                    condition="reference",
                    query=q,
                    extra={
                        "card_id": card_id,
                        "set_id": set_info.get("id"),
                        "rarity": row.get("rarity"),
                        "tcgplayer_prices": prices,
                        "catalog": True,
                    },
                )
            )
    return _dedupe(items)


def _pokemontcg_query(raw: str) -> str:
    text = raw.strip()
    # "Charizard Base 4/102" → name:"Charizard" set.name:"Base" number:4
    parts = text.split()
    if len(parts) >= 1:
        name = parts[0]
        clauses = [f'name:"{name}"']
        number = next((p for p in parts if "/" in p or p.isdigit()), None)
        if number:
            clauses.append(f"number:{number.split('/')[0]}")
        set_bits = [p for p in parts[1:] if p != number and not p.isdigit()]
        # Drop common edition words from set clause.
        set_bits = [
            p
            for p in set_bits
            if p.lower() not in {"1st", "edition", "first", "shadowless", "unlimited", "holo"}
        ]
        if set_bits:
            clauses.append(f'set.name:"{" ".join(set_bits)}"')
        return " ".join(clauses)
    return f'name:"{text}"'


def _extract_tcgplayer_prices(row: dict[str, Any]) -> dict[str, float]:
    tcg = row.get("tcgplayer") or {}
    prices = tcg.get("prices") or {}
    out: dict[str, float] = {}
    for _variant, vals in prices.items():
        if not isinstance(vals, dict):
            continue
        for key in ("market", "mid", "low", "high"):
            value = vals.get(key)
            if isinstance(value, (int, float)) and key not in out:
                out[key] = float(value)
    return out


def collect_ebay_api(
    http: Http,
    settings: Settings,
    limit: int,
    *,
    query: str | None = None,
) -> list[CardListing]:
    """Optional eBay Browse API when EBAY_APP_ID / OAuth token is configured."""
    if not collector_enabled("ebay_api"):
        return []
    token = getattr(settings, "ebay_oauth_token", "") or ""
    app_id = getattr(settings, "ebay_app_id", "") or ""
    if not token and not app_id:
        return []
    items: list[CardListing] = []
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for q in build_queries(query)[: max(1, min(4, limit))]:
        full_q = f"{q} pokemon"
        # Browse API needs OAuth; Finding API works with app id (legacy).
        if token:
            data = http.get_json(
                "https://api.ebay.com/buy/browse/v1/item_summary/search",
                params={"q": full_q, "limit": min(20, limit)},
                headers=headers,
            )
            if not isinstance(data, dict):
                continue
            for row in data.get("itemSummaries") or []:
                url = row.get("itemWebUrl") or ""
                title = row.get("title") or ""
                if not url or not title:
                    continue
                price = ((row.get("price") or {}).get("value"))
                image = (row.get("image") or {}).get("imageUrl")
                items.append(
                    listing(
                        source="ebay",
                        url=url,
                        title=title,
                        body=row.get("condition") or "",
                        price_usd=float(price) if price is not None else None,
                        image_urls=[image] if image else [],
                        seller=((row.get("seller") or {}).get("username")),
                        condition=row.get("condition"),
                        query=full_q,
                        extra={"engine": "ebay_browse"},
                    )
                )
        elif app_id:
            data = http.get_json(
                "https://svcs.ebay.com/services/search/FindingService/v1",
                params={
                    "OPERATION-NAME": "findItemsByKeywords",
                    "SERVICE-VERSION": "1.0.0",
                    "SECURITY-APPNAME": app_id,
                    "RESPONSE-DATA-FORMAT": "JSON",
                    "keywords": full_q,
                    "paginationInput.entriesPerPage": min(20, limit),
                },
            )
            if not isinstance(data, dict):
                continue
            ack = data.get("findItemsByKeywordsResponse") or []
            if not ack:
                continue
            search = (ack[0].get("searchResult") or [{}])[0]
            for row in search.get("item") or []:
                url = (row.get("viewItemURL") or [""])[0]
                title = (row.get("title") or [""])[0]
                if not url or not title:
                    continue
                selling = (row.get("sellingStatus") or [{}])[0]
                price = ((selling.get("currentPrice") or [{}])[0]).get("__value__")
                gallery = (row.get("galleryURL") or [None])[0]
                items.append(
                    listing(
                        source="ebay",
                        url=url,
                        title=title,
                        body="",
                        price_usd=float(price) if price is not None else None,
                        image_urls=[gallery] if gallery else [],
                        query=full_q,
                        extra={"engine": "ebay_finding"},
                    )
                )
    return _dedupe(items)


def collect_inbox(
    http: Http,
    settings: Settings,
    limit: int,
    *,
    query: str | None = None,
) -> list[CardListing]:
    """Manual marketplace exports dropped into data/cards/inbox/."""
    del http, settings, query
    if not collector_enabled("inbox"):
        return []
    directory = Path(collector_conf("inbox").get("directory") or "data/cards/inbox")
    if not directory.is_absolute():
        from scrapertc.settings import repo_root

        directory = repo_root() / directory
    if not directory.exists():
        return []
    items: list[CardListing] = []
    for path in sorted(directory.glob("*")):
        if path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        text = path.read_text(encoding="utf-8")
        rows: list[dict[str, Any]]
        if path.suffix.lower() == ".jsonl":
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            payload = json.loads(text)
            rows = payload if isinstance(payload, list) else [payload]
        for row in rows[:limit]:
            items.append(
                listing(
                    source=str(row.get("source") or "inbox"),
                    url=str(row.get("url") or ""),
                    title=str(row.get("title") or ""),
                    body=str(row.get("body") or row.get("description") or ""),
                    price_usd=row.get("price_usd"),
                    image_urls=list(row.get("image_urls") or []),
                    seller=row.get("seller"),
                    condition=row.get("condition"),
                    query=str(row.get("query") or path.name),
                    extra=dict(row.get("extra") or {"inbox_file": path.name}),
                )
            )
    return _dedupe(items)


CARD_COLLECTORS = {
    "brave_markets": collect_brave_markets,
    "pokemontcg": collect_pokemontcg,
    "ebay_api": collect_ebay_api,
    "inbox": collect_inbox,
}

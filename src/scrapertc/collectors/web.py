from __future__ import annotations

from typing import Any

import feedparser

from scrapertc.collectors import collector_conf, enabled, item
from scrapertc.http import Http
from scrapertc.models import ChatterItem
from scrapertc.settings import (
    Settings,
    is_broad,
    live_queries,
    mention_queries,
    player_queries,
    web_scopes,
)


def collect_rss(http: Http, settings: Settings, limit: int) -> list[ChatterItem]:
    if not enabled("rss") and not enabled("news"):
        return []
    del settings
    items: list[ChatterItem] = []
    for feed in collector_conf("rss").get("feeds") or []:
        url = feed.get("url")
        name = feed.get("name") or "rss"
        if not url:
            continue
        text = http.get_text(url)
        if not text:
            continue
        parsed = feedparser.parse(text)
        for entry in parsed.entries[:limit]:
            link = getattr(entry, "link", "") or ""
            title = getattr(entry, "title", "") or ""
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
            published = getattr(entry, "published", None) or getattr(entry, "updated", None)
            if not title:
                continue
            items.append(
                item(
                    source="news" if "google.com" in url else "rss",
                    url=link,
                    title=title,
                    body=_strip_html(summary),
                    author=getattr(entry, "author", None),
                    published_at=published,
                    query=name,
                )
            )
    return _dedupe(items)


def collect_google_cse(http: Http, settings: Settings, limit: int) -> list[ChatterItem]:
    if not enabled("google_cse"):
        return []
    if not (settings.google_api_key and settings.google_cse_id):
        return []
    items: list[ChatterItem] = []
    queries = live_queries(priority_cap=12, broad_cap=20)
    for query in queries:
        for scope in web_scopes():
            q = f"{query} {scope}".strip()
            data = http.get_json(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": settings.google_api_key,
                    "cx": settings.google_cse_id,
                    "q": q,
                    "num": min(10, limit),
                    "dateRestrict": "m3",
                },
            )
            if not isinstance(data, dict):
                continue
            for result in data.get("items") or []:
                link = result.get("link") or ""
                title = result.get("title") or ""
                snippet = result.get("snippet") or ""
                if not link or not title:
                    continue
                source = _source_from_url(link)
                items.append(
                    item(
                        source=source,
                        url=link,
                        title=title,
                        body=snippet,
                        published_at=_cse_date(result),
                        query=q,
                        extra={"display_link": result.get("displayLink")},
                    )
                )
    return _dedupe(items)


def _cse_date(result: dict[str, Any]) -> str | None:
    meta = ((result.get("pagemap") or {}).get("metatags") or [{}])[0]
    return meta.get("article:published_time") or meta.get("og:updated_time")


def _source_from_url(url: str) -> str:
    host = url.lower()
    if "linkedin.com" in host:
        return "linkedin"
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "patents.google.com" in host:
        return "patent"
    if "researchgate.net" in host:
        return "researchgate"
    if "edu" in host:
        return "lab"
    return "web"


def _strip_html(text: str) -> str:
    out = []
    skip = False
    for char in text:
        if char == "<":
            skip = True
            continue
        if char == ">":
            skip = False
            out.append(" ")
            continue
        if not skip:
            out.append(char)
    return "".join(out)


def _dedupe(items: list[ChatterItem]) -> list[ChatterItem]:
    seen: set[str] = set()
    unique: list[ChatterItem] = []
    for entry in items:
        if entry.id in seen:
            continue
        seen.add(entry.id)
        unique.append(entry)
    return unique


def collect_youtube(http: Http, settings: Settings, limit: int) -> list[ChatterItem]:
    if not enabled("youtube"):
        return []
    items: list[ChatterItem] = []
    for channel_id in collector_conf("youtube").get("channel_ids") or []:
        text = http.get_text(
            "https://www.youtube.com/feeds/videos.xml",
            params={"channel_id": channel_id},
        )
        if not text:
            continue
        parsed = feedparser.parse(text)
        for entry in parsed.entries[:limit]:
            items.append(
                item(
                    source="youtube",
                    url=getattr(entry, "link", "") or "",
                    title=getattr(entry, "title", "") or "",
                    body=getattr(entry, "summary", "") or "",
                    author=getattr(entry, "author", None),
                    published_at=getattr(entry, "published", None),
                    query=f"channel:{channel_id}",
                )
            )
    if not settings.youtube_api_key:
        return _dedupe(items)
    for query in live_queries(priority_cap=12, broad_cap=20):
        data = http.get_json(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": query,
                "type": "video",
                "order": "date",
                "maxResults": min(limit, 25),
                "key": settings.youtube_api_key,
            },
        )
        if not isinstance(data, dict):
            continue
        for row in data.get("items") or []:
            video_id = (row.get("id") or {}).get("videoId")
            snippet = row.get("snippet") or {}
            if not video_id:
                continue
            items.append(
                item(
                    source="youtube",
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    title=snippet.get("title") or "",
                    body=snippet.get("description") or "",
                    author=(snippet.get("channelTitle")),
                    published_at=snippet.get("publishedAt"),
                    query=query,
                    extra={"channel_id": snippet.get("channelId")},
                )
            )
    return _dedupe(items)


def collect_brave(http: Http, settings: Settings, limit: int) -> list[ChatterItem]:
    """Independent web index — the Gate 1 replacement for Google CSE."""
    if not enabled("brave"):
        return []
    if not settings.brave_api_key:
        return []
    items: list[ChatterItem] = []
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": settings.brave_api_key,
    }
    mentions = mention_queries()[: 16 if is_broad() else 12]
    players = player_queries()
    # First mention queries get every site: scope; the rest are unscoped to save quota.
    full_scope_n = 8
    for index, query in enumerate(mentions):
        scopes = web_scopes() if index < full_scope_n else [""]
        for scope in scopes:
            items.extend(
                _brave_hits(
                    http,
                    headers,
                    query,
                    scope,
                    limit,
                    offsets=[0, 1] if not scope else [0],
                )
            )
    # Named competitors: open web + LinkedIn. Anyone mentioning them is a lead after Gate 2.
    for name in players:
        for scope in ("", "site:linkedin.com"):
            items.extend(_brave_hits(http, headers, name, scope, limit, offsets=[0]))
    return _dedupe(items)


def _brave_hits(
    http: Http,
    headers: dict[str, str],
    query: str,
    scope: str,
    limit: int,
    offsets: list[int],
) -> list[ChatterItem]:
    items: list[ChatterItem] = []
    q = f"{query} {scope}".strip()
    for offset in offsets:
        data = http.get_json(
            "https://api.search.brave.com/res/v1/web/search",
            params={
                "q": q,
                "count": min(20, max(limit, 10)),
                "offset": offset,
                "freshness": "pm",
                "country": "us",
                "search_lang": "en",
            },
            headers=headers,
        )
        if not isinstance(data, dict):
            break
        results = (data.get("web") or {}).get("results") or []
        if not results:
            break
        for row in results:
            url = row.get("url") or ""
            title = row.get("title") or ""
            if not url or not title:
                continue
            items.append(
                item(
                    source=_source_from_url(url),
                    url=url,
                    title=title,
                    body=row.get("description") or "",
                    published_at=row.get("page_age") or row.get("age"),
                    query=q,
                    extra={"engine": "brave"},
                )
            )
    return items

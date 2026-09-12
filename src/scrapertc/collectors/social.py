from __future__ import annotations

from typing import Any

from scrapertc.collectors import collector_conf, enabled, item
from scrapertc.http import Http
from scrapertc.models import ChatterItem
from scrapertc.settings import Settings, search_queries


def collect_reddit(http: Http, settings: Settings, limit: int) -> list[ChatterItem]:
    if not enabled("reddit"):
        return []
    conf = collector_conf("reddit")
    token = _reddit_token(http, settings)
    headers = {"Authorization": f"bearer {token}"} if token else None
    host = "https://oauth.reddit.com" if token else "https://www.reddit.com"
    items: list[ChatterItem] = []
    reddit_q = str(conf.get("search_query") or "cannabis tissue culture OR meristem OR HLVd")
    for query in search_queries()[:6]:
        data = http.get_json(
            f"{host}/search.json",
            params={"q": query, "sort": "new", "limit": min(limit, 100), "t": "month"},
            headers=headers,
        )
        items.extend(_reddit_children(data, query))
    listing_subs = conf.get("subreddits") or []
    search_subs = list(listing_subs) + list(conf.get("search_subreddits") or [])
    for sub in search_subs:
        data = http.get_json(
            f"{host}/r/{sub}/search.json",
            params={
                "q": reddit_q,
                "restrict_sr": "1",
                "sort": "new",
                "limit": min(limit, 100),
            },
            headers=headers,
        )
        items.extend(_reddit_children(data, f"r/{sub}"))
    for sub in listing_subs:
        listing = http.get_json(
            f"{host}/r/{sub}/new.json",
            params={"limit": min(limit, 50)},
            headers=headers,
        )
        items.extend(_reddit_children(listing, f"r/{sub}/new"))
    return _dedupe(items)


def _reddit_token(http: Http, settings: Settings) -> str | None:
    if not (settings.reddit_client_id and settings.reddit_client_secret):
        return None
    auth = (settings.reddit_client_id, settings.reddit_client_secret)
    response = http.post(
        "https://www.reddit.com/api/v1/access_token",
        data={"grant_type": "client_credentials"},
        auth=auth,
    )
    if response.status_code != 200:
        return None
    try:
        return response.json().get("access_token")
    except ValueError:
        return None


def _reddit_children(payload: Any, query: str) -> list[ChatterItem]:
    if not isinstance(payload, dict):
        return []
    children = ((payload.get("data") or {}).get("children")) or []
    out: list[ChatterItem] = []
    for child in children:
        data = child.get("data") or {}
        permalink = data.get("permalink") or ""
        url = data.get("url") or ""
        if permalink:
            url = f"https://www.reddit.com{permalink}"
        title = data.get("title") or ""
        body = data.get("selftext") or ""
        if not title:
            continue
        out.append(
            item(
                source="reddit",
                url=url,
                title=title,
                body=body,
                author=data.get("author"),
                published_at=data.get("created_utc"),
                query=query,
                extra={
                    "subreddit": data.get("subreddit"),
                    "score": data.get("score"),
                    "num_comments": data.get("num_comments"),
                },
            )
        )
    return out


def collect_hackernews(http: Http, settings: Settings, limit: int) -> list[ChatterItem]:
    if not enabled("hackernews"):
        return []
    del settings
    items: list[ChatterItem] = []
    for query in search_queries()[:6]:
        data = http.get_json(
            "https://hn.algolia.com/api/v1/search",
            params={"query": query, "hitsPerPage": min(limit, 50), "tags": "story"},
        )
        if not isinstance(data, dict):
            continue
        for hit in data.get("hits") or []:
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            title = hit.get("title") or ""
            if not title:
                continue
            items.append(
                item(
                    source="hackernews",
                    url=url,
                    title=title,
                    body=hit.get("story_text") or "",
                    author=hit.get("author"),
                    published_at=hit.get("created_at"),
                    query=query,
                    extra={"points": hit.get("points"), "num_comments": hit.get("num_comments")},
                )
            )
    return _dedupe(items)


def collect_bluesky(http: Http, settings: Settings, limit: int) -> list[ChatterItem]:
    if not enabled("bluesky"):
        return []
    del settings
    items: list[ChatterItem] = []
    for query in search_queries()[:6]:
        data = http.get_json(
            "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
            params={"q": query, "limit": min(limit, 50)},
        )
        if not isinstance(data, dict):
            continue
        for post in data.get("posts") or []:
            author = (post.get("author") or {}).get("handle")
            record = post.get("record") or {}
            uri = post.get("uri") or ""
            rkey = uri.rsplit("/", 1)[-1] if uri else ""
            url = f"https://bsky.app/profile/{author}/post/{rkey}" if author and rkey else uri
            text = record.get("text") or ""
            if not text:
                continue
            items.append(
                item(
                    source="bluesky",
                    url=url,
                    title=text[:140],
                    body=text,
                    author=author,
                    published_at=record.get("createdAt") or post.get("indexedAt"),
                    query=query,
                )
            )
    return _dedupe(items)


def _dedupe(items: list[ChatterItem]) -> list[ChatterItem]:
    seen: set[str] = set()
    unique: list[ChatterItem] = []
    for entry in items:
        if entry.id in seen:
            continue
        seen.add(entry.id)
        unique.append(entry)
    return unique

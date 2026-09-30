from __future__ import annotations

from typing import Any

from scrapertc.collectors import collector_conf, enabled, item
from scrapertc.http import Http
from scrapertc.models import ChatterItem
from scrapertc.settings import Settings, live_queries


def collect_reddit(http: Http, settings: Settings, limit: int) -> list[ChatterItem]:
    if not enabled("reddit"):
        return []
    conf = collector_conf("reddit")
    token = _reddit_token(http, settings)
    headers = {"Authorization": f"bearer {token}"} if token else None
    host = "https://oauth.reddit.com" if token else "https://www.reddit.com"
    items: list[ChatterItem] = []
    reddit_q = str(conf.get("search_query") or "cannabis tissue culture OR meristem OR HLVd")
    for query in live_queries(priority_cap=20, broad_cap=36):
        items.extend(
            _reddit_paged(
                http,
                f"{host}/search.json",
                {"q": query, "sort": "new", "limit": min(limit, 100), "t": "month"},
                headers,
                query,
            )
        )
    listing_subs = conf.get("subreddits") or []
    search_subs = list(listing_subs) + list(conf.get("search_subreddits") or [])
    for sub in search_subs:
        items.extend(
            _reddit_paged(
                http,
                f"{host}/r/{sub}/search.json",
                {
                    "q": reddit_q,
                    "restrict_sr": "1",
                    "sort": "new",
                    "limit": min(limit, 100),
                },
                headers,
                f"r/{sub}",
            )
        )
    for sub in listing_subs:
        items.extend(
            _reddit_paged(
                http,
                f"{host}/r/{sub}/new.json",
                {"limit": min(limit, 50)},
                headers,
                f"r/{sub}/new",
            )
        )
    return _dedupe(items)


def _reddit_paged(
    http: Http,
    url: str,
    params: dict[str, Any],
    headers: dict[str, str] | None,
    query: str,
    pages: int = 2,
) -> list[ChatterItem]:
    items: list[ChatterItem] = []
    after = None
    for _ in range(pages):
        page_params = dict(params)
        if after:
            page_params["after"] = after
        data = http.get_json(url, params=page_params, headers=headers)
        items.extend(_reddit_children(data, query))
        nxt = ((data or {}).get("data") or {}).get("after") if isinstance(data, dict) else None
        if not nxt or nxt == after:
            break
        after = nxt
    return items


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
    for query in live_queries(priority_cap=20, broad_cap=36):
        for page in range(2):
            data = http.get_json(
                "https://hn.algolia.com/api/v1/search",
                params={
                    "query": query,
                    "hitsPerPage": min(limit, 50),
                    "tags": "story",
                    "page": page,
                },
            )
            if not isinstance(data, dict):
                break
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
                        extra={
                            "points": hit.get("points"),
                            "num_comments": hit.get("num_comments"),
                        },
                    )
                )
            if page + 1 >= int(data.get("nbPages") or 1):
                break
    return _dedupe(items)


def collect_bluesky(http: Http, settings: Settings, limit: int) -> list[ChatterItem]:
    if not enabled("bluesky"):
        return []
    del settings
    items: list[ChatterItem] = []
    for query in live_queries(priority_cap=20, broad_cap=36):
        cursor: str | None = None
        for _page in range(2):
            params: dict[str, Any] = {"q": query, "limit": min(limit, 50)}
            if cursor:
                params["cursor"] = cursor
            data = http.get_json(
                "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
                params=params,
            )
            if not isinstance(data, dict):
                break
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
            cursor = data.get("cursor")
            if not cursor:
                break
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

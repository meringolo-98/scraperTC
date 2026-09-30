from __future__ import annotations

from scrapertc.collectors import enabled, item
from scrapertc.http import Http
from scrapertc.models import ChatterItem
from scrapertc.settings import Settings, live_queries


def collect_github(http: Http, settings: Settings, limit: int) -> list[ChatterItem]:
    if not enabled("github"):
        return []
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    items: list[ChatterItem] = []
    for query in live_queries(priority_cap=4, broad_cap=8):
        repos = http.get_json(
            "https://api.github.com/search/repositories",
            params={"q": query, "sort": "updated", "per_page": min(limit, 30)},
            headers=headers,
        )
        if isinstance(repos, dict):
            for row in repos.get("items") or []:
                items.append(
                    item(
                        source="github",
                        url=row.get("html_url") or "",
                        title=row.get("full_name") or "",
                        body=row.get("description") or "",
                        author=(row.get("owner") or {}).get("login"),
                        published_at=row.get("updated_at"),
                        query="repo",
                        extra={"stars": row.get("stargazers_count")},
                    )
                )
        issues = http.get_json(
            "https://api.github.com/search/issues",
            params={
                "q": f"{query} in:title,body",
                "sort": "updated",
                "per_page": min(limit, 30),
            },
            headers=headers,
        )
        if isinstance(issues, dict):
            for row in issues.get("items") or []:
                items.append(
                    item(
                        source="github",
                        url=row.get("html_url") or "",
                        title=row.get("title") or "",
                        body=(row.get("body") or "")[:1500],
                        author=(row.get("user") or {}).get("login"),
                        published_at=row.get("updated_at"),
                        query="issue",
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

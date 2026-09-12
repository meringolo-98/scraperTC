from __future__ import annotations

from typing import Any

from scrapertc.collectors import collector_conf, enabled, item
from scrapertc.http import Http
from scrapertc.models import ChatterItem
from scrapertc.settings import Settings, search_queries


def collect_openalex(http: Http, settings: Settings, limit: int) -> list[ChatterItem]:
    if not enabled("openalex"):
        return []
    items: list[ChatterItem] = []
    headers = {"User-Agent": settings.user_agent}
    for query in search_queries()[:3]:
        data = http.get_json(
            "https://api.openalex.org/works",
            params={
                "search": query,
                "per_page": min(limit, 50),
                "sort": "publication_date:desc",
                "mailto": settings.contact_email,
            },
            headers=headers,
        )
        if not isinstance(data, dict):
            continue
        for work in data.get("results") or []:
            parsed = _openalex_item(work, query)
            if parsed:
                items.append(parsed)
    return _dedupe(items)


def _openalex_item(work: dict[str, Any], query: str) -> ChatterItem | None:
    title = work.get("display_name") or ""
    if not title:
        return None
    url = (work.get("primary_location") or {}).get("landing_page_url") or work.get("id") or ""
    abstract = _openalex_abstract(work.get("abstract_inverted_index"))
    authors = [
        (auth.get("author") or {}).get("display_name")
        for auth in (work.get("authorships") or [])[:4]
        if (auth.get("author") or {}).get("display_name")
    ]
    institutions = []
    for auth in work.get("authorships") or []:
        for inst in auth.get("institutions") or []:
            name = inst.get("display_name")
            if name:
                institutions.append(name)
    return item(
        source="openalex",
        url=url,
        title=title,
        body=abstract,
        author=", ".join(authors) or None,
        published_at=work.get("publication_date"),
        query=query,
        extra={
            "cited_by": work.get("cited_by_count"),
            "labs": institutions[:8],
            "doi": (work.get("ids") or {}).get("doi"),
        },
    )


def _openalex_abstract(inverted: dict[str, list[int]] | None) -> str:
    if not inverted:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for idx in idxs:
            positions.append((idx, word))
    positions.sort()
    return " ".join(word for _, word in positions)[:2000]


def collect_pubmed(http: Http, settings: Settings, limit: int) -> list[ChatterItem]:
    if not enabled("pubmed"):
        return []
    term = '("tissue culture"[Title/Abstract] AND (plant OR micropropagation OR meristem))'
    search = http.get_json(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params={
            "db": "pubmed",
            "term": term,
            "retmax": min(limit, 50),
            "retmode": "json",
            "sort": "pub+date",
            "email": settings.contact_email,
        },
    )
    if not isinstance(search, dict):
        return []
    ids = ((search.get("esearchresult") or {}).get("idlist")) or []
    if not ids:
        return []
    summary = http.get_json(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        params={
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "json",
            "email": settings.contact_email,
        },
    )
    if not isinstance(summary, dict):
        return []
    result = summary.get("result") or {}
    items: list[ChatterItem] = []
    for pmid in ids:
        row = result.get(pmid) or {}
        title = row.get("title") or ""
        if not title:
            continue
        items.append(
            item(
                source="pubmed",
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                title=title,
                body=row.get("source") or "",
                author=_first_author(row),
                published_at=row.get("pubdate") or row.get("sortpubdate"),
                query="pubmed-plant-tc",
                extra={"pmid": pmid, "journal": row.get("fulljournalname")},
            )
        )
    return items


def _first_author(row: dict[str, Any]) -> str | None:
    authors = row.get("authors") or []
    if authors:
        return authors[0].get("name")
    return None


def collect_arxiv(http: Http, settings: Settings, limit: int) -> list[ChatterItem]:
    if not enabled("arxiv"):
        return []
    del settings
    text = http.get_text(
        "https://export.arxiv.org/api/query",
        params={
            "search_query": 'all:"tissue culture" AND (plant OR micropropagation)',
            "start": 0,
            "max_results": min(limit, 40),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        },
    )
    if not text:
        return []
    import feedparser

    parsed = feedparser.parse(text)
    items: list[ChatterItem] = []
    for entry in parsed.entries:
        items.append(
            item(
                source="arxiv",
                url=getattr(entry, "link", "") or "",
                title=getattr(entry, "title", "") or "",
                body=getattr(entry, "summary", "") or "",
                author=getattr(entry, "author", None),
                published_at=getattr(entry, "published", None),
                query="arxiv-plant-tc",
            )
        )
    return items


def collect_stackexchange(http: Http, settings: Settings, limit: int) -> list[ChatterItem]:
    if not enabled("stackexchange"):
        return []
    del settings
    items: list[ChatterItem] = []
    for site in collector_conf("stackexchange").get("sites") or ["biology"]:
        data = http.get_json(
            "https://api.stackexchange.com/2.3/search/advanced",
            params={
                "q": "tissue culture",
                "site": site,
                "pagesize": min(limit, 30),
                "sort": "creation",
                "order": "desc",
                "filter": "default",
            },
        )
        if not isinstance(data, dict):
            continue
        for row in data.get("items") or []:
            items.append(
                item(
                    source="stackexchange",
                    url=row.get("link") or "",
                    title=row.get("title") or "",
                    body=" ".join(row.get("tags") or []),
                    author=((row.get("owner") or {}).get("display_name")),
                    published_at=row.get("creation_date"),
                    query=site,
                    extra={"score": row.get("score"), "site": site},
                )
            )
    return _dedupe(items)


def _dedupe(items: list[ChatterItem]) -> list[ChatterItem]:
    seen: set[str] = set()
    unique: list[ChatterItem] = []
    for entry in items:
        if not entry or entry.id in seen:
            continue
        seen.add(entry.id)
        unique.append(entry)
    return unique

from __future__ import annotations

from scrapertc.collectors.social import collect_hackernews, collect_reddit
from scrapertc.collectors.web import collect_rss, collect_youtube
from scrapertc.settings import Settings


class FakeHttp:
    def __init__(self, json_map=None, text_map=None):
        self.json_map = json_map or {}
        self.text_map = text_map or {}
        self.calls: list[str] = []

    def get_json(self, url, params=None, headers=None, auth=None, ok_statuses=None):
        self.calls.append(url)
        for key, value in self.json_map.items():
            if key in url:
                return value
        return None

    def get_text(self, url, params=None):
        self.calls.append(url)
        for key, value in self.text_map.items():
            if key in url:
                return value
        return None

    def post(self, *args, **kwargs):
        class Resp:
            status_code = 400

            def json(self):
                return {}

        return Resp()


def test_reddit_parses_listing() -> None:
    http = FakeHttp(
        json_map={
            "reddit.com": {
                "data": {
                    "children": [
                        {
                            "data": {
                                "title": "Tissue culture banana flasks",
                                "selftext": "MS medium recipe",
                                "permalink": "/r/tissuecultureplants/comments/abc/flask/",
                                "author": "tc",
                                "created_utc": 1700000000,
                                "subreddit": "tissuecultureplants",
                                "score": 12,
                                "num_comments": 3,
                            }
                        }
                    ]
                }
            }
        }
    )
    items = collect_reddit(http, Settings(), limit=5)
    assert items
    assert items[0].source == "reddit"
    assert "banana" in items[0].title.lower()
    assert items[0].url.startswith("https://www.reddit.com/")


def test_hn_parses_hits() -> None:
    http = FakeHttp(
        json_map={
            "hn.algolia.com": {
                "hits": [
                    {
                        "title": "Micropropagation robot",
                        "url": "https://example.com/hn",
                        "author": "pg",
                        "created_at": "2026-01-01T00:00:00Z",
                        "objectID": "1",
                        "points": 10,
                        "num_comments": 2,
                    }
                ]
            }
        }
    )
    items = collect_hackernews(http, Settings(), limit=5)
    assert items[0].url == "https://example.com/hn"


def test_rss_google_news() -> None:
    feed = """<?xml version="1.0" encoding="UTF-8" ?>
    <rss version="2.0"><channel>
      <title>News</title>
      <item>
        <title>Plant tissue culture lab expands</title>
        <link>https://news.example.com/tc</link>
        <description>Oglesby Plants opened a wing.</description>
        <pubDate>Mon, 01 Sep 2026 12:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """
    http = FakeHttp(text_map={"news.google.com": feed})
    items = collect_rss(http, Settings(), limit=10)
    assert any("tissue culture" in item.title.lower() for item in items)


def test_youtube_search() -> None:
    http = FakeHttp(
        json_map={
            "googleapis.com/youtube": {
                "items": [
                    {
                        "id": {"videoId": "abc123"},
                        "snippet": {
                            "title": "Orchid flasking",
                            "description": "tissue culture at home",
                            "channelTitle": "TC",
                            "publishedAt": "2026-01-02T00:00:00Z",
                            "channelId": "chan",
                        },
                    }
                ]
            }
        }
    )
    settings = Settings(youtube_api_key="fake")
    items = collect_youtube(http, settings, limit=5)
    assert items[0].url.endswith("abc123")


def test_brave_parses_web_results() -> None:
    from scrapertc.collectors.web import collect_brave

    http = FakeHttp(
        json_map={
            "search.brave.com": {
                "web": {
                    "results": [
                        {
                            "url": "https://example.com/cannabis-meristem",
                            "title": "Cannabis meristem lab opens",
                            "description": "HLVd clean stock",
                            "page_age": "2026-01-01",
                        }
                    ]
                }
            }
        }
    )
    items = collect_brave(http, Settings(brave_api_key="fake"), limit=5)
    assert items
    assert items[0].extra.get("engine") == "brave"
    assert "meristem" in items[0].title.lower()


def test_semanticscholar_parses_papers() -> None:
    from scrapertc.collectors.scholarly import collect_semanticscholar

    http = FakeHttp(
        json_map={
            "semanticscholar.org": {
                "data": [
                    {
                        "paperId": "abc",
                        "title": "Genomic selection in Cannabis sativa",
                        "abstract": "GBLUP for chemotype",
                        "url": "https://www.semanticscholar.org/paper/abc",
                        "year": 2024,
                        "publicationDate": "2024-03-01",
                        "authors": [{"name": "Ada"}],
                        "externalIds": {"DOI": "10.1/xyz"},
                    }
                ]
            }
        }
    )
    items = collect_semanticscholar(http, Settings(), limit=5)
    assert items
    assert items[0].source == "semanticscholar"
    assert "genomic" in items[0].title.lower()


def test_crossref_parses_works() -> None:
    from scrapertc.collectors.scholarly import collect_crossref

    http = FakeHttp(
        json_map={
            "api.crossref.org": {
                "message": {
                    "items": [
                        {
                            "DOI": "10.1000/tc",
                            "URL": "https://doi.org/10.1000/tc",
                            "title": ["Hop latent viroid in cannabis meristem"],
                            "abstract": "clean stock",
                            "author": [{"given": "Ada", "family": "Lovelace"}],
                            "issued": {"date-parts": [[2025, 4, 1]]},
                            "container-title": ["Plant Cell Reports"],
                        }
                    ]
                }
            }
        }
    )
    items = collect_crossref(http, Settings(), limit=5)
    assert items
    assert items[0].source == "crossref"
    assert items[0].extra.get("doi") == "10.1000/tc"


def test_reddit_stops_when_after_repeats() -> None:
    from scrapertc.collectors.social import _reddit_paged

    http = FakeHttp(
        json_map={
            "reddit.com": {
                "data": {
                    "after": "t3_abc",
                    "children": [
                        {
                            "data": {
                                "title": "Meristem flask",
                                "selftext": "",
                                "permalink": "/r/tissuecultureplants/comments/abc/flask/",
                                "author": "tc",
                                "created_utc": 1700000000,
                            }
                        }
                    ],
                }
            }
        }
    )
    items = _reddit_paged(
        http,
        "https://www.reddit.com/search.json",
        {"q": "meristem", "limit": 5},
        None,
        "meristem",
        pages=5,
    )
    assert items
    assert len(http.calls) == 2

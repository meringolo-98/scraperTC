from __future__ import annotations

from scrapertc.demo import demo_items
from scrapertc.gate2.report import render_markdown
from scrapertc.models import canonicalize_url, make_item_id
from scrapertc.pipeline import collect, refine, report
from scrapertc.store import Store


def test_canonicalize_strips_tracking() -> None:
    url = "https://www.Example.com/path/?utm_source=x&keep=1"
    assert canonicalize_url(url) == "https://example.com/path?keep=1"


def test_ids_are_stable() -> None:
    assert make_item_id("reddit", "https://a.example/p") == make_item_id(
        "reddit", "https://www.a.example/p/"
    )


def test_upsert_is_idempotent(store: Store) -> None:
    items = demo_items()
    store.upsert_items(items)
    store.upsert_items(items)
    assert store.counts()["chatter"] == len(items)


def test_pipeline_demo(tmp_path, settings) -> None:
    store = Store(settings.db_path)
    stats = collect(items=demo_items(), store=store, settings=settings)
    assert stats["collected"] == len(demo_items())
    refined = refine(store=store)
    assert refined["labeled"] >= 3
    paths = report(store=store, out_dir=tmp_path / "reports")
    markdown = (tmp_path / "reports" / "latest.md").read_text(encoding="utf-8")
    assert "Competition" in markdown
    assert "Breakthroughs" in markdown
    assert "Saturation" in markdown
    assert "Cannabis TC" in markdown
    assert paths["html"].endswith(".html")


def test_report_lists_entities() -> None:
    # classified_rows shape used by the reporter
    rows = [
        {
            "title": "PCT kit",
            "url": "https://example.com",
            "source": "web",
            "domain": "plant",
            "body": "launched",
            "labels": ["competition"],
            "competition": 0.9,
            "breakthrough": 0.0,
            "saturation": 0.0,
            "entities": ["Plant Cell Technology"],
        }
    ]
    text = render_markdown(rows)
    assert "Plant Cell Technology" in text

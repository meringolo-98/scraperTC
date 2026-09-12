from __future__ import annotations

from collections.abc import Callable

from scrapertc.collectors.github import collect_github
from scrapertc.collectors.inbox import collect_inbox
from scrapertc.collectors.scholarly import (
    collect_arxiv,
    collect_openalex,
    collect_pubmed,
    collect_stackexchange,
)
from scrapertc.collectors.social import collect_bluesky, collect_hackernews, collect_reddit
from scrapertc.collectors.web import collect_google_cse, collect_rss, collect_youtube
from scrapertc.gate2 import classify
from scrapertc.gate2.report import write_reports
from scrapertc.http import Http
from scrapertc.models import ChatterItem, utcnow
from scrapertc.settings import Settings, get_settings, repo_root
from scrapertc.store import Store

CollectorMap = dict[str, Callable[..., list[ChatterItem]]]

COLLECTORS: CollectorMap = {
    "reddit": collect_reddit,
    "hackernews": collect_hackernews,
    "bluesky": collect_bluesky,
    "rss": collect_rss,
    "youtube": collect_youtube,
    "google_cse": collect_google_cse,
    "openalex": collect_openalex,
    "pubmed": collect_pubmed,
    "arxiv": collect_arxiv,
    "stackexchange": collect_stackexchange,
    "github": collect_github,
    "inbox": collect_inbox,
}


def open_store(settings: Settings | None = None) -> Store:
    settings = settings or get_settings()
    return Store(settings.db_path)


def collect(
    *,
    only: list[str] | None = None,
    limit: int | None = None,
    settings: Settings | None = None,
    store: Store | None = None,
    items: list[ChatterItem] | None = None,
) -> dict[str, int | str]:
    settings = settings or get_settings()
    store = store or open_store(settings)
    started = utcnow()
    selected = only or list(COLLECTORS)
    unknown = [name for name in selected if name not in COLLECTORS]
    cap = limit or settings.default_limit
    gathered: list[ChatterItem] = list(items or [])
    errors: dict[str, str] = {}
    per_source: dict[str, int] = {}

    if items is None:
        http = Http(settings)
        try:
            for name in selected:
                if name not in COLLECTORS:
                    continue
                try:
                    batch = COLLECTORS[name](http, settings, cap)
                except Exception as exc:  # collectors must not kill the run
                    errors[name] = str(exc)
                    batch = []
                per_source[name] = len(batch)
                gathered.extend(batch)
        finally:
            http.close()

    written = store.upsert_items(gathered)
    stats: dict[str, int | str] = {
        "collected": len(gathered),
        "upserted": written,
        **{f"collector:{k}": v for k, v in per_source.items()},
    }
    if unknown:
        stats["unknown_collectors"] = ",".join(unknown)
    if errors:
        stats["errors"] = "; ".join(f"{k}: {v}" for k, v in errors.items())
    store.record_run("collect", started, stats)
    return stats


def refine(*, store: Store | None = None) -> dict[str, int]:
    store = store or open_store()
    started = utcnow()
    items = store.all_items()
    signals = [classify(item) for item in items]
    store.upsert_signals(signals)
    labeled = sum(1 for signal in signals if signal.labels)
    stats = {"items": len(items), "signals": len(signals), "labeled": labeled}
    store.record_run("refine", started, stats)
    return stats


def report(*, store: Store | None = None, out_dir=None) -> dict[str, str]:
    store = store or open_store()
    destination = out_dir or (repo_root() / "data" / "reports")
    paths = write_reports(store.classified_rows(), destination)
    return {kind: str(path) for kind, path in paths.items()}

from __future__ import annotations

from pathlib import Path

from scrapertc.cards.collectors import CARD_COLLECTORS
from scrapertc.cards.config import budget_cap, cards_config, steal_config
from scrapertc.cards.models import CardListing, utcnow
from scrapertc.cards.report import write_card_reports
from scrapertc.cards.steal import find_steals
from scrapertc.cards.store import CardStore
from scrapertc.cards.vision import analyze_listings
from scrapertc.http import Http
from scrapertc.settings import Settings, get_settings, repo_root


def cards_db_path(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    override = getattr(settings, "scrapertc_cards_db", "") or ""
    if override:
        path = Path(override)
    else:
        path = repo_root() / "data" / "cards.db"
    if not path.is_absolute():
        path = repo_root() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def open_card_store(settings: Settings | None = None) -> CardStore:
    return CardStore(cards_db_path(settings))


def collect_cards(
    *,
    query: str | None = None,
    only: list[str] | None = None,
    sites: list[str] | None = None,
    limit: int | None = None,
    settings: Settings | None = None,
    store: CardStore | None = None,
    items: list[CardListing] | None = None,
) -> dict[str, int | str]:
    """Secondary Gate 1 — marketplace + catalog intake under shared scrape budget."""
    settings = settings or get_settings()
    store = store or open_card_store(settings)
    started = utcnow()
    cap = budget_cap(settings.default_limit, limit)
    selected = only or list(CARD_COLLECTORS)
    unknown = [name for name in selected if name not in CARD_COLLECTORS]
    gathered: list[CardListing] = list(items or [])
    errors: dict[str, str] = {}
    per_source: dict[str, int] = {}

    if items is None:
        http = Http(settings)
        try:
            for name in selected:
                if name not in CARD_COLLECTORS:
                    continue
                try:
                    fn = CARD_COLLECTORS[name]
                    if name == "brave_markets":
                        batch = fn(http, settings, cap, query=query, sites=sites)
                    else:
                        batch = fn(http, settings, cap, query=query)
                except Exception as exc:  # collectors must not kill the run
                    errors[name] = str(exc)
                    batch = []
                per_source[name] = len(batch)
                gathered.extend(batch)
        finally:
            http.close()

    written = store.upsert_listings(gathered)
    stats: dict[str, int | str] = {
        "product": "cards",
        "collected": len(gathered),
        "new": written["new"],
        "updated": written["updated"],
        "upserted": written["written"],
        "budget_cap": cap,
        "budget_share": str(cards_config().get("budget_share") or 0.25),
        **{f"collector:{k}": v for k, v in per_source.items()},
    }
    if query:
        stats["query"] = query
    if unknown:
        stats["unknown_collectors"] = ",".join(unknown)
    if errors:
        stats["errors"] = "; ".join(f"{k}: {v}" for k, v in errors.items())
    store.record_run("cards_collect", started, stats)
    return stats


def analyze_grades(
    *,
    store: CardStore | None = None,
    settings: Settings | None = None,
    limit: int | None = None,
    fetch: bool = True,
) -> dict[str, int | str]:
    settings = settings or get_settings()
    store = store or open_card_store(settings)
    started = utcnow()
    cfg_limit = int(cards_config().get("image_analyze_limit") or 8)
    cap = limit or cfg_limit
    listings = store.all_listings()
    cache_dir = repo_root() / "data" / "cards" / "images"
    http = Http(settings) if fetch else None
    try:
        reports = analyze_listings(
            listings,
            http=http,
            limit=cap,
            cache_dir=cache_dir,
        )
    finally:
        if http is not None:
            http.close()
    written = store.upsert_grades(reports)
    defected = sum(1 for r in reports if r.defects)
    stats: dict[str, int | str] = {
        "analyzed": len(reports),
        "written": written,
        "with_defects": defected,
    }
    store.record_run("cards_vision", started, stats)
    return stats


def detect_steals(
    *,
    store: CardStore | None = None,
    settings: Settings | None = None,
) -> dict[str, int | str]:
    settings = settings or get_settings()
    store = store or open_card_store(settings)
    started = utcnow()
    hits = find_steals(store.all_listings())
    written = store.upsert_steals(hits)
    min_score = float(steal_config().get("min_score") or 0.55)
    stats: dict[str, int | str] = {
        "candidates": written,
        "above_threshold": sum(1 for h in hits if h.score >= min_score),
        "min_score": min_score,
    }
    store.record_run("cards_steals", started, stats)
    return stats


def report_cards(
    *,
    store: CardStore | None = None,
    out_dir: Path | None = None,
) -> dict[str, str]:
    store = store or open_card_store()
    destination = out_dir or (repo_root() / "data" / "cards" / "reports")
    paths = write_card_reports(store.enriched_rows(), store.steal_rows(), destination)
    return {kind: str(path) for kind, path in paths.items()}


def run_cards(
    *,
    query: str | None = None,
    only: list[str] | None = None,
    sites: list[str] | None = None,
    limit: int | None = None,
    settings: Settings | None = None,
    store: CardStore | None = None,
    items: list[CardListing] | None = None,
    skip_vision: bool = False,
) -> dict[str, dict[str, int | str] | dict[str, str]]:
    settings = settings or get_settings()
    store = store or open_card_store(settings)
    collect_stats = collect_cards(
        query=query,
        only=only,
        sites=sites,
        limit=limit,
        settings=settings,
        store=store,
        items=items,
    )
    vision_stats: dict[str, int | str] = {"skipped": 1}
    if not skip_vision:
        # Demo / offline path still runs CV on any embedded fixture bytes via cache.
        vision_stats = analyze_grades(
            store=store,
            settings=settings,
            fetch=items is None,
        )
    steal_stats = detect_steals(store=store, settings=settings)
    paths = report_cards(store=store)
    return {
        "collect": collect_stats,
        "vision": vision_stats,
        "steals": steal_stats,
        "report": paths,
    }

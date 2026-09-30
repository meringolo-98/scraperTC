from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from scrapertc import __version__
from scrapertc.cards.config import budget_cap, enabled_sites
from scrapertc.cards.demo import demo_card_listings
from scrapertc.cards.pipeline import (
    analyze_grades,
    collect_cards,
    detect_steals,
    open_card_store,
    report_cards,
    run_cards,
)
from scrapertc.cards.store import CardStore
from scrapertc.demo import demo_items
from scrapertc.pipeline import COLLECTORS, collect, open_store, refine, report
from scrapertc.settings import get_settings

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Cannabis TC chatter scraper + secondary Pokemon card intake. Not a chatbot.",
)
cards_app = typer.Typer(
    no_args_is_help=True,
    help="Secondary product: find Pokemon cards on eBay/TCG/etc, grade photos, flag steals.",
)
app.add_typer(cards_app, name="cards")
console = Console()


def _print_stats(title: str, stats: dict) -> None:
    table = Table(title=title)
    table.add_column("key")
    table.add_column("value")
    for key, value in stats.items():
        table.add_row(str(key), str(value))
    console.print(table)


@app.command("collect")
def collect_cmd(
    only: str | None = typer.Option(
        None, "--only", help="Comma-separated collectors (reddit,youtube,pubmed,...)."
    ),
    limit: int | None = typer.Option(None, "--limit", help="Per-collector cap."),
    demo: bool = typer.Option(
        False, "--demo", help="Load bundled sample chatter instead of the network."
    ),
    broad: bool = typer.Option(
        False,
        "--broad",
        help="Also search generic plant-TC phrases (noisier). Gate 2 still filters.",
    ),
) -> None:
    """Gate 1 — scrape configured sources into SQLite. No LLM."""
    names = [part.strip() for part in only.split(",")] if only else None
    items = demo_items() if demo else None
    _print_stats("Gate 1 collect", collect(only=names, limit=limit, items=items, broad=broad))


@app.command("refine")
def refine_cmd() -> None:
    """Gate 2 — deterministic scores (competition / breakthrough / saturation). Optional."""
    _print_stats("Gate 2 refine", refine())


@app.command("report")
def report_cmd() -> None:
    """Write markdown, HTML, and JSON reports from the local store."""
    paths = report()
    console.print("Wrote reports:")
    for kind, path in paths.items():
        console.print(f"  {kind}: {path}")


@app.command("run")
def run_cmd(
    demo: bool = typer.Option(False, "--demo", help="Offline fixture run (no API keys)."),
    only: str | None = typer.Option(
        None, "--only", help="Comma-separated collectors for live intake."
    ),
    limit: int | None = typer.Option(None, "--limit"),
    broad: bool = typer.Option(
        False,
        "--broad",
        help="Also search generic plant-TC phrases (noisier). Gate 2 still filters.",
    ),
) -> None:
    """Collect, refine, and report in one pass."""
    names = [part.strip() for part in only.split(",")] if only else None
    items = demo_items() if demo else None
    _print_stats("Gate 1 collect", collect(only=names, limit=limit, items=items, broad=broad))
    _print_stats("Gate 2 refine", refine())
    paths = report()
    console.print(f"Report: {paths['html']}")


@app.command("status")
def status_cmd() -> None:
    """Show local store counts and which collectors can run without keys."""
    settings = get_settings()
    store = open_store(settings)
    counts = store.counts()
    table = Table(title="scraperTC store")
    table.add_column("key")
    table.add_column("value")
    table.add_row("version", __version__)
    table.add_row("db", str(settings.db_path))
    for key, value in sorted(counts.items()):
        table.add_row(key, str(value))
    console.print(table)

    ready = Table(title="collectors")
    ready.add_column("name")
    ready.add_column("needs")
    ready.add_column("ready")
    needs = {
        "youtube": "YOUTUBE_API_KEY (channel RSS still works)",
        "brave": "BRAVE_API_KEY — web-wide index",
        "google_cse": "GOOGLE_API_KEY + GOOGLE_CSE_ID (legacy; Brave preferred)",
        "reddit": "optional REDDIT_CLIENT_ID/SECRET",
        "github": "optional GITHUB_TOKEN",
        "semanticscholar": "optional SEMANTIC_SCHOLAR_API_KEY",
    }
    for name in COLLECTORS:
        extra = needs.get(name, "public API")
        ok = "yes"
        if name == "brave" and not settings.brave_api_key:
            ok = "waiting on key"
        if name == "google_cse" and not (settings.google_api_key and settings.google_cse_id):
            ok = "waiting on keys"
        if name == "youtube" and not settings.youtube_api_key:
            ok = "search waiting on key"
        ready.add_row(name, extra, ok)
    console.print(ready)
    console.print(
        "Secondary product: [bold]scrapertc cards status[/bold] "
        f"(budget_cap={budget_cap(settings.default_limit)})"
    )


@app.command("export")
def export_cmd(
    out: Path = typer.Option(Path("data/export.jsonl"), "--out", help="JSONL destination."),
    labeled: bool = typer.Option(
        False, "--labeled", help="Only rows that already have Gate 2 labels."
    ),
) -> None:
    """Dump the SQLite store to JSONL. This is the product: rows, not chat."""
    settings = get_settings()
    store = open_store(settings)
    n = store.export_jsonl(out, labeled_only=labeled)
    console.print(f"exported {n} rows → {out}")


@cards_app.command("find")
def cards_find_cmd(
    query: str = typer.Argument(..., help="Card search, e.g. 'Charizard Base 4/102 1st edition'."),
    sites: str | None = typer.Option(
        None,
        "--sites",
        help="Comma-separated site keys from config/cards.yaml (ebay,tcgplayer,...).",
    ),
    only: str | None = typer.Option(
        None,
        "--only",
        help="Collectors: brave_markets,pokemontcg,ebay_api,inbox.",
    ),
    limit: int | None = typer.Option(
        None, "--limit", help="Override secondary budget cap for this run."
    ),
    analyze: bool = typer.Option(
        True, "--analyze/--no-analyze", help="Run visual grade heuristics on listing images."
    ),
    steals: bool = typer.Option(
        True, "--steals/--no-steals", help="Flag underpriced / mislisted valuable variants."
    ),
) -> None:
    """Find a specific card across marketplace scopes + Pokemon TCG catalog."""
    site_list = [p.strip() for p in sites.split(",")] if sites else None
    only_list = [p.strip() for p in only.split(",")] if only else None
    stats = collect_cards(query=query, only=only_list, sites=site_list, limit=limit)
    _print_stats("cards collect", stats)
    if analyze:
        _print_stats("cards vision", analyze_grades(limit=limit))
    if steals:
        _print_stats("cards steals", detect_steals())
    paths = report_cards()
    console.print(f"Report: {paths['html']}")


@cards_app.command("collect")
def cards_collect_cmd(
    query: str | None = typer.Option(None, "--query", help="Optional override of watchlist."),
    sites: str | None = typer.Option(None, "--sites"),
    only: str | None = typer.Option(None, "--only"),
    limit: int | None = typer.Option(None, "--limit"),
    demo: bool = typer.Option(False, "--demo", help="Offline fixtures, no network."),
) -> None:
    """Intake marketplace + catalog hits into data/cards.db (shared scrape budget)."""
    site_list = [p.strip() for p in sites.split(",")] if sites else None
    only_list = [p.strip() for p in only.split(",")] if only else None
    items = demo_card_listings() if demo else None
    _print_stats(
        "cards collect",
        collect_cards(
            query=query,
            only=only_list,
            sites=site_list,
            limit=limit,
            items=items,
        ),
    )


@cards_app.command("analyze")
def cards_analyze_cmd(
    limit: int | None = typer.Option(None, "--limit", help="Max images to inspect."),
    no_fetch: bool = typer.Option(
        False, "--no-fetch", help="Only use cached images under data/cards/images/."
    ),
) -> None:
    """Visual grade defects: centering, edge whitening, corner wear (deterministic CV)."""
    _print_stats("cards vision", analyze_grades(limit=limit, fetch=not no_fetch))


@cards_app.command("steals")
def cards_steals_cmd() -> None:
    """Flag listings that look mis-titled relative to a higher-value variant."""
    _print_stats("cards steals", detect_steals())
    store = open_card_store()
    rows = store.steal_rows(min_score=0.0)
    table = Table(title="steal candidates")
    table.add_column("score")
    table.add_column("title")
    table.add_column("listed_as")
    table.add_column("suspected")
    table.add_column("price")
    for row in rows[:30]:
        price = row.get("listed_price")
        table.add_row(
            str(row.get("score")),
            str(row.get("title") or "")[:60],
            str(row.get("listed_as") or ""),
            str(row.get("suspected") or ""),
            f"${price:.0f}" if isinstance(price, (int, float)) else "",
        )
    console.print(table)


@cards_app.command("run")
def cards_run_cmd(
    query: str | None = typer.Option(None, "--query"),
    sites: str | None = typer.Option(None, "--sites"),
    only: str | None = typer.Option(None, "--only"),
    limit: int | None = typer.Option(None, "--limit"),
    demo: bool = typer.Option(False, "--demo"),
    skip_vision: bool = typer.Option(False, "--skip-vision"),
) -> None:
    """Collect → vision → steals → report for the cards product."""
    site_list = [p.strip() for p in sites.split(",")] if sites else None
    only_list = [p.strip() for p in only.split(",")] if only else None
    items = demo_card_listings() if demo else None
    result = run_cards(
        query=query,
        only=only_list,
        sites=site_list,
        limit=limit,
        items=items,
        skip_vision=skip_vision or demo,
    )
    _print_stats("cards collect", result["collect"])  # type: ignore[arg-type]
    _print_stats("cards vision", result["vision"])  # type: ignore[arg-type]
    _print_stats("cards steals", result["steals"])  # type: ignore[arg-type]
    console.print(f"Report: {result['report']['html']}")  # type: ignore[index]


@cards_app.command("status")
def cards_status_cmd() -> None:
    """Show cards DB counts, enabled sites, and shared budget cap."""
    settings = get_settings()
    store = open_card_store(settings)
    counts = store.counts()
    table = Table(title="scraperTC cards (secondary)")
    table.add_column("key")
    table.add_column("value")
    table.add_row("version", __version__)
    table.add_row("db", str(store.path))
    table.add_row("budget_cap", str(budget_cap(settings.default_limit)))
    table.add_row("request_delay_seconds", str(settings.request_delay_seconds))
    table.add_row("user_agent", settings.user_agent)
    for key, value in sorted(counts.items()):
        table.add_row(key, str(value))
    console.print(table)

    sites = Table(title="marketplace scopes")
    sites.add_column("site")
    sites.add_column("scope")
    for name, conf in enabled_sites().items():
        sites.add_row(name, str(conf.get("scope") or ""))
    console.print(sites)

    ready = Table(title="card collectors")
    ready.add_column("name")
    ready.add_column("needs")
    ready.add_column("ready")
    ready.add_row(
        "brave_markets",
        "BRAVE_API_KEY (shared with Gate 1)",
        "yes" if settings.brave_api_key else "waiting on key",
    )
    ready.add_row("pokemontcg", "public API (optional POKEMONTCG_API_KEY)", "yes")
    ebay_ready = "yes" if (settings.ebay_oauth_token or settings.ebay_app_id) else "optional keys"
    ready.add_row("ebay_api", "EBAY_OAUTH_TOKEN or EBAY_APP_ID", ebay_ready)
    ready.add_row("inbox", "data/cards/inbox JSON/JSONL", "yes")
    console.print(ready)


@cards_app.command("export")
def cards_export_cmd(
    out: Path = typer.Option(Path("data/cards/export.jsonl"), "--out"),
    steals_only: bool = typer.Option(False, "--steals-only"),
) -> None:
    """Dump card listings (+ grades / steals) to JSONL."""
    store: CardStore = open_card_store()
    n = store.export_jsonl(out, steals_only=steals_only)
    console.print(f"exported {n} rows → {out}")


@cards_app.command("report")
def cards_report_cmd() -> None:
    """Write cards markdown/HTML/JSON reports."""
    paths = report_cards()
    console.print("Wrote reports:")
    for kind, path in paths.items():
        console.print(f"  {kind}: {path}")


if __name__ == "__main__":
    app()

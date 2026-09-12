from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from scrapertc import __version__
from scrapertc.demo import demo_items
from scrapertc.pipeline import COLLECTORS, collect, open_store, refine, report
from scrapertc.settings import get_settings

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Cannabis TC chatter scraper: collect, store, dump. Not a chatbot.",
)
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


if __name__ == "__main__":
    app()

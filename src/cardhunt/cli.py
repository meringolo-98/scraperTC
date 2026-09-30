from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from cardhunt import __version__
from cardhunt.engine import hunt, listings, status_payload
from cardhunt.server import serve
from cardhunt.settings import get_settings

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="CardHunt — phone/desktop Pokemon card finder. No TC pipeline required.",
)
console = Console()


def _stats(title: str, stats: dict) -> None:
    table = Table(title=title)
    table.add_column("key")
    table.add_column("value")
    for key, value in stats.items():
        if isinstance(value, dict):
            value = ", ".join(f"{k}={v}" for k, v in value.items())
        table.add_row(str(key), str(value))
    console.print(table)


@app.command("serve")
def serve_cmd(
    host: str | None = typer.Option(None, "--host", help="Bind address (default 0.0.0.0)."),
    port: int | None = typer.Option(None, "--port", help="Port (default 8787)."),
) -> None:
    """Start the phone-friendly web UI. Open it on your phone over Wi‑Fi."""
    settings = get_settings()
    serve(host=host or settings.host, port=port or settings.port)


@app.command("hunt")
def hunt_cmd(
    query: str = typer.Argument(..., help="Card to find, e.g. 'Charizard Base 4/102'."),
    sites: str = typer.Option(
        "ebay,tcgplayer,pricecharting,mercari",
        "--sites",
        help="Comma-separated marketplaces.",
    ),
    limit: int | None = typer.Option(None, "--limit"),
    demo: bool = typer.Option(False, "--demo", help="Offline fixtures, no keys."),
) -> None:
    """CLI hunt (same engine as the phone UI)."""
    site_list = [s.strip() for s in sites.split(",") if s.strip()]
    result = hunt(query=query, sites=site_list, limit=limit, demo=demo, skip_vision=demo)
    _stats("hunt", result["collect"])  # type: ignore[index]
    _stats("steals", result["steals"])  # type: ignore[index]
    rows = listings(steals_only=True)
    if rows:
        table = Table(title="steal hits")
        table.add_column("score")
        table.add_column("title")
        table.add_column("suspected")
        table.add_column("price")
        for row in rows[:20]:
            price = row.get("listed_price")
            table.add_row(
                str(row.get("score")),
                str(row.get("title") or "")[:50],
                str(row.get("suspected") or ""),
                f"${price:.0f}" if isinstance(price, (int, float)) else "",
            )
        console.print(table)


@app.command("demo")
def demo_cmd() -> None:
    """Offline demo — works on phone Termux / laptop with no API keys."""
    result = hunt(query="Charizard Base 4/102", demo=True, skip_vision=True)
    _stats("demo collect", result["collect"])  # type: ignore[index]
    _stats("demo steals", result["steals"])  # type: ignore[index]
    console.print("Tip: cardhunt serve  → open the UI on your phone.")


@app.command("status")
def status_cmd() -> None:
    _stats(f"CardHunt {__version__}", status_payload())


if __name__ == "__main__":
    app()

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_card_reports(
    rows: list[dict[str, Any]],
    steals: list[dict[str, Any]],
    out_dir: Path,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "cards.json"
    md_path = out_dir / "cards.md"
    html_path = out_dir / "cards.html"
    steals_path = out_dir / "steals.json"

    json_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    steals_path.write_text(json.dumps(steals, indent=2, default=str), encoding="utf-8")
    md_path.write_text(_markdown(rows, steals), encoding="utf-8")
    html_path.write_text(_html(rows, steals), encoding="utf-8")
    return {
        "json": json_path,
        "markdown": md_path,
        "html": html_path,
        "steals": steals_path,
    }


def _markdown(rows: list[dict[str, Any]], steals: list[dict[str, Any]]) -> str:
    lines = [
        "# Pokemon card scrape report",
        "",
        f"Listings: **{len(rows)}** · Steal candidates: **{len(steals)}**",
        "",
        "## Steals",
        "",
    ]
    if not steals:
        lines.append("_No steal candidates above threshold._")
        lines.append("")
    else:
        for row in steals[:40]:
            price = row.get("listed_price")
            price_s = f"${price:.0f}" if isinstance(price, (int, float)) else "?"
            lines.append(
                f"- **{row.get('title') or row.get('listing_id')}** "
                f"({row.get('source')}) score={row.get('score')} "
                f"listed_as={row.get('listed_as')} → suspected={row.get('suspected')} "
                f"price={price_s}"
            )
            for reason in row.get("reasons") or []:
                lines.append(f"  - {reason}")
            if row.get("url"):
                lines.append(f"  - {row['url']}")
        lines.append("")

    lines.extend(["## Listings", ""])
    for row in rows[:80]:
        defects = ", ".join(row.get("defects") or []) or "none"
        grade = row.get("grade_band") or "n/a"
        steal = row.get("steal_score")
        steal_s = f" steal={steal}" if steal else ""
        price = row.get("price_usd")
        price_s = f"${price:.2f}" if isinstance(price, (int, float)) else "?"
        lines.append(
            f"- [{row.get('source')}] {row.get('title')} — {price_s} "
            f"grade={grade} defects={defects}{steal_s}"
        )
        if row.get("url"):
            lines.append(f"  - {row['url']}")
    lines.append("")
    return "\n".join(lines)


def _html(rows: list[dict[str, Any]], steals: list[dict[str, Any]]) -> str:
    steal_items = []
    for row in steals[:40]:
        reasons = "".join(f"<li>{_esc(r)}</li>" for r in (row.get("reasons") or []))
        steal_items.append(
            "<li>"
            f"<strong>{_esc(row.get('title') or row.get('listing_id'))}</strong> "
            f"score={row.get('score')} · {_esc(row.get('listed_as'))} → "
            f"{_esc(row.get('suspected'))}"
            f"<ul>{reasons}</ul>"
            f"<a href=\"{_esc(row.get('url'))}\">listing</a>"
            "</li>"
        )
    listing_items = []
    for row in rows[:80]:
        listing_items.append(
            "<li>"
            f"[{_esc(row.get('source'))}] {_esc(row.get('title'))} — "
            f"grade={_esc(row.get('grade_band'))} "
            f"defects={_esc(', '.join(row.get('defects') or []) or 'none')}"
            f"<br/><a href=\"{_esc(row.get('url'))}\">open</a>"
            "</li>"
        )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"/><title>Pokemon card scrape</title>
<style>
body {{ font-family: Georgia, serif; margin: 2rem; background: #f7f3ea; color: #1c1917; }}
h1,h2 {{ font-family: "Trebuchet MS", sans-serif; }}
a {{ color: #9a3412; }}
</style></head><body>
<h1>Pokemon card scrape</h1>
<p>{len(rows)} listings · {len(steals)} steal candidates</p>
<h2>Steals</h2>
<ul>{"".join(steal_items) or "<li>None</li>"}</ul>
<h2>Listings</h2>
<ul>{"".join(listing_items)}</ul>
</body></html>
"""


def _esc(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

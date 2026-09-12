from __future__ import annotations

import html
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scrapertc.models import utcnow


def write_reports(rows: list[dict[str, Any]], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().strftime("%Y%m%d-%H%M%S")
    md_path = out_dir / f"chatter-{stamp}.md"
    html_path = out_dir / f"chatter-{stamp}.html"
    json_path = out_dir / f"chatter-{stamp}.json"
    latest_md = out_dir / "latest.md"
    latest_html = out_dir / "latest.html"
    latest_json = out_dir / "latest.json"

    payload = {
        "generated_at": utcnow().isoformat(),
        "totals": _totals(rows),
        "items": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    markdown = render_markdown(rows)
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(render_html(rows), encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")
    latest_html.write_text(html_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    return {"markdown": md_path, "html": html_path, "json": json_path}


def _totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = Counter()
    sources = Counter()
    domains = Counter()
    for row in rows:
        sources[row.get("source") or "unknown"] += 1
        domains[row.get("domain") or "unclassified"] += 1
        for label in row.get("labels") or []:
            labels[label] += 1
    return {
        "items": len(rows),
        "labels": dict(labels),
        "sources": dict(sources),
        "domains": dict(domains),
    }


def render_markdown(rows: list[dict[str, Any]]) -> str:
    totals = _totals(rows)
    lines = [
        "# Tissue culture chatter",
        "",
        f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}.",
        "",
        "## Intake (Gate 1)",
        "",
        f"- **{totals['items']}** unique items",
        f"- Sources: {_fmt_counts(totals['sources'])}",
        f"- Domains: {_fmt_counts(totals['domains'])}",
        "",
        "## Gate 2 scores",
        "",
        f"- Labels: {_fmt_counts(totals['labels']) or 'none yet — run `scrapertc refine`'}",
        "",
    ]
    for heading, label in (
        ("Competition", "competition"),
        ("Breakthroughs", "breakthrough"),
        ("Saturation", "saturation"),
    ):
        lines.extend(_section(heading, rows, label))
    leftover = [
        row
        for row in rows
        if not set(row.get("labels") or []) & {"competition", "breakthrough", "saturation"}
    ]
    lines.extend(_section("Unscored / watch list", leftover, None, cap=15))
    return "\n".join(lines).rstrip() + "\n"


def _section(
    heading: str,
    rows: list[dict[str, Any]],
    label: str | None,
    cap: int = 25,
) -> list[str]:
    if label:
        picked = [row for row in rows if label in (row.get("labels") or [])]
        picked.sort(key=lambda row: float(row.get(label) or 0), reverse=True)
    else:
        picked = rows
    lines = [f"### {heading}", "", f"{len(picked)} items.", ""]
    if not picked:
        lines.append("_Nothing in this bucket yet._")
        lines.append("")
        return lines
    for row in picked[:cap]:
        title = row.get("title") or "(untitled)"
        url = row.get("url") or ""
        source = row.get("source") or "?"
        domain = row.get("domain") or "?"
        entities = ", ".join(row.get("entities") or [])
        score = ""
        if label:
            score = f" · {label} {float(row.get(label) or 0):.2f}"
        lines.append(f"- **[{title}]({url})** ({source}, {domain}{score})")
        body = (row.get("body") or "").strip()
        if body:
            lines.append(f"  {body[:280]}{'…' if len(body) > 280 else ''}")
        if entities:
            lines.append(f"  Entities: {entities}")
        lines.append("")
    return lines


def _fmt_counts(counts: dict[str, int]) -> str:
    if not counts:
        return ""
    return ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def render_html(rows: list[dict[str, Any]]) -> str:
    totals = _totals(rows)
    sections = []
    for heading, label in (
        ("Competition", "competition"),
        ("Breakthroughs", "breakthrough"),
        ("Saturation", "saturation"),
    ):
        sections.append(_html_section(heading, rows, label))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Tissue culture chatter</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 0; background: #101218; color: #e8eaed; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 32px 20px 80px; }}
    h1 {{ font-weight: 650; letter-spacing: -0.03em; }}
    .meta {{ color: #9aa0a6; }}
    .chips span {{ display: inline-block; background: #1f2430; border: 1px solid #2c3344; border-radius: 999px; padding: 4px 10px; margin: 0 6px 6px 0; font-size: 13px; }}
    article {{ background: #181c27; border: 1px solid #2c3344; border-radius: 12px; padding: 14px 16px; margin: 10px 0; }}
    article a {{ color: #8ab4ff; text-decoration: none; }}
    .src {{ color: #9aa0a6; font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }}
    .body {{ color: #c5c9d1; font-size: 14px; line-height: 1.45; }}
    h2 {{ margin-top: 2.2rem; }}
  </style>
</head>
<body>
<main>
  <h1>Tissue culture chatter</h1>
  <p class="meta">Gate 1 intake · Gate 2 competition / breakthrough / saturation</p>
  <p class="chips">{_chips(totals)}</p>
  {"".join(sections)}
</main>
</body>
</html>
"""


def _chips(totals: dict[str, Any]) -> str:
    bits = [f"<span>{totals['items']} items</span>"]
    for key, value in (totals.get("labels") or {}).items():
        bits.append(f"<span>{html.escape(str(key))} {value}</span>")
    return "".join(bits)


def _html_section(heading: str, rows: list[dict[str, Any]], label: str) -> str:
    picked = [row for row in rows if label in (row.get("labels") or [])]
    picked.sort(key=lambda row: float(row.get(label) or 0), reverse=True)
    cards = []
    for row in picked[:40]:
        title = html.escape(row.get("title") or "(untitled)")
        url = html.escape(row.get("url") or "#")
        body = html.escape((row.get("body") or "")[:360])
        source = html.escape(str(row.get("source") or ""))
        score = float(row.get(label) or 0)
        entities = html.escape(", ".join(row.get("entities") or []))
        entity_html = f'<p class="meta">{entities}</p>' if entities else ""
        cards.append(
            f'<article><div class="src">{source} · {label} {score:.2f}</div>'
            f'<h3><a href="{url}">{title}</a></h3>'
            f'<p class="body">{body}</p>'
            f"{entity_html}"
            "</article>"
        )
    inner = "".join(cards) or "<p class='meta'>Nothing in this bucket yet.</p>"
    return f"<h2>{heading} ({len(picked)})</h2>{inner}"

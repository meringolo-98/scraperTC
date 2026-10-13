from __future__ import annotations

import json
from pathlib import Path

from scrapertc.collectors import collector_conf, enabled, item
from scrapertc.http import Http
from scrapertc.models import ChatterItem
from scrapertc.settings import Settings, repo_root


def collect_inbox(http: Http, settings: Settings, limit: int) -> list[ChatterItem]:
    """Drop exports (LinkedIn, newsletters, manual copies) as JSONL into data/inbox."""
    if not enabled("inbox"):
        return []
    del http, settings
    directory = Path(collector_conf("inbox").get("directory") or "data/inbox")
    if not directory.is_absolute():
        directory = repo_root() / directory
    if not directory.exists():
        return []
    items: list[ChatterItem] = []
    files = sorted(directory.glob("*.jsonl")) + sorted(directory.glob("*.json"))
    for path in files:
        if path.name.startswith("."):
            continue
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            continue
        records: list[dict] = []
        if path.suffix == ".jsonl":
            for line in raw.splitlines():
                records.append(json.loads(line))
        else:
            loaded = json.loads(raw)
            records = loaded if isinstance(loaded, list) else [loaded]
        for row in records[:limit]:
            url = str(row.get("url") or "")
            title = str(row.get("title") or "")
            if not url and not title:
                continue
            items.append(
                item(
                    source=str(row.get("source") or "inbox"),
                    url=url or f"inbox://{path.name}/{title}",
                    title=title,
                    body=str(row.get("body") or ""),
                    author=row.get("author"),
                    published_at=row.get("published_at"),
                    query=str(row.get("query") or path.stem),
                    extra={"file": path.name},
                )
            )
    return items

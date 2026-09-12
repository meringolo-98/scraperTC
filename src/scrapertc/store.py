from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from scrapertc.models import ChatterItem, Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS chatter (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    body TEXT,
    author TEXT,
    published_at TEXT,
    collected_at TEXT NOT NULL,
    first_seen TEXT,
    last_seen TEXT,
    hit_count INTEGER DEFAULT 1,
    query TEXT,
    extra_json TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    item_id TEXT PRIMARY KEY,
    domain TEXT,
    competition REAL,
    breakthrough REAL,
    saturation REAL,
    relevance REAL,
    labels_json TEXT,
    segments_json TEXT,
    entities_json TEXT,
    rationale TEXT,
    classified_at TEXT,
    FOREIGN KEY (item_id) REFERENCES chatter(id)
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gate TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    stats_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_chatter_source ON chatter(source);
CREATE INDEX IF NOT EXISTS idx_chatter_published ON chatter(published_at);
CREATE INDEX IF NOT EXISTS idx_signals_domain ON signals(domain);
"""


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        signal_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(signals)")}
        if signal_cols and "relevance" not in signal_cols:
            self._conn.execute("ALTER TABLE signals ADD COLUMN relevance REAL DEFAULT 0")
        if signal_cols and "segments_json" not in signal_cols:
            self._conn.execute("ALTER TABLE signals ADD COLUMN segments_json TEXT")
        chatter_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(chatter)")}
        if chatter_cols and "first_seen" not in chatter_cols:
            self._conn.execute("ALTER TABLE chatter ADD COLUMN first_seen TEXT")
        if chatter_cols and "last_seen" not in chatter_cols:
            self._conn.execute("ALTER TABLE chatter ADD COLUMN last_seen TEXT")
        if chatter_cols and "hit_count" not in chatter_cols:
            self._conn.execute("ALTER TABLE chatter ADD COLUMN hit_count INTEGER DEFAULT 1")
        self._conn.execute(
            """
            UPDATE chatter
            SET first_seen = COALESCE(first_seen, collected_at),
                last_seen = COALESCE(last_seen, collected_at),
                hit_count = COALESCE(hit_count, 1)
            """
        )

    def close(self) -> None:
        self._conn.close()

    def upsert_items(self, items: Iterable[ChatterItem]) -> dict[str, int]:
        new = 0
        updated = 0
        for item in items:
            extra = json.dumps(item.extra)
            seen = item.collected_at.isoformat()
            published = item.published_at.isoformat() if item.published_at else None
            existing = self._conn.execute(
                "SELECT id FROM chatter WHERE id = ?", (item.id,)
            ).fetchone()
            if existing:
                self._conn.execute(
                    """
                    UPDATE chatter SET
                        title = ?,
                        body = ?,
                        author = ?,
                        published_at = COALESCE(?, published_at),
                        last_seen = ?,
                        hit_count = COALESCE(hit_count, 1) + 1,
                        extra_json = ?
                    WHERE id = ?
                    """,
                    (item.title, item.body, item.author, published, seen, extra, item.id),
                )
                updated += 1
            else:
                self._conn.execute(
                    """
                    INSERT INTO chatter (
                        id, source, url, title, body, author, published_at,
                        collected_at, first_seen, last_seen, hit_count, query, extra_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        item.id,
                        item.source,
                        item.url,
                        item.title,
                        item.body,
                        item.author,
                        published,
                        seen,
                        seen,
                        seen,
                        item.query,
                        extra,
                    ),
                )
                new += 1
        self._conn.commit()
        return {"new": new, "updated": updated, "written": new + updated}

    def export_jsonl(self, path: Path, *, labeled_only: bool = False) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = self.classified_rows()
        if labeled_only:
            rows = [row for row in rows if row.get("labels")]
        n = 0
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                n += 1
        return n

    def upsert_signals(self, signals: Iterable[Signal]) -> int:
        count = 0
        for signal in signals:
            row = signal.as_row()
            self._conn.execute(
                """
                INSERT INTO signals (
                    item_id, domain, competition, breakthrough, saturation,
                    relevance, labels_json, segments_json, entities_json,
                    rationale, classified_at
                ) VALUES (
                    :item_id, :domain, :competition, :breakthrough, :saturation,
                    :relevance, :labels_json, :segments_json, :entities_json,
                    :rationale, :classified_at
                )
                ON CONFLICT(item_id) DO UPDATE SET
                    domain=excluded.domain,
                    competition=excluded.competition,
                    breakthrough=excluded.breakthrough,
                    saturation=excluded.saturation,
                    relevance=excluded.relevance,
                    labels_json=excluded.labels_json,
                    segments_json=excluded.segments_json,
                    entities_json=excluded.entities_json,
                    rationale=excluded.rationale,
                    classified_at=excluded.classified_at
                """,
                row,
            )
            count += 1
        self._conn.commit()
        return count

    def record_run(self, gate: str, started_at: datetime, stats: dict[str, Any]) -> None:
        finished = datetime.now(started_at.tzinfo) if started_at.tzinfo else datetime.now()
        self._conn.execute(
            "INSERT INTO runs (gate, started_at, finished_at, stats_json) VALUES (?, ?, ?, ?)",
            (
                gate,
                started_at.isoformat(),
                finished.isoformat(),
                json.dumps(stats),
            ),
        )
        self._conn.commit()

    def all_items(self) -> list[ChatterItem]:
        rows = self._conn.execute("SELECT * FROM chatter ORDER BY collected_at DESC").fetchall()
        return [self._item_from_row(row) for row in rows]

    def classified_rows(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT c.*, s.domain, s.competition, s.breakthrough, s.saturation,
                   s.relevance, s.labels_json, s.segments_json, s.entities_json,
                   s.rationale
            FROM chatter c
            LEFT JOIN signals s ON s.item_id = c.id
            ORDER BY
                COALESCE(s.relevance, 0) DESC,
                COALESCE(s.competition, 0) + COALESCE(s.breakthrough, 0)
                + COALESCE(s.saturation, 0) DESC,
                c.collected_at DESC
            """
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data["labels"] = json.loads(data.pop("labels_json") or "[]")
            data["segments"] = json.loads(data.pop("segments_json") or "[]")
            data["entities"] = json.loads(data.pop("entities_json") or "[]")
            extra = data.pop("extra_json")
            data["extra"] = json.loads(extra) if extra else {}
            out.append(data)
        return out

    def counts(self) -> dict[str, int]:
        chatter = self._conn.execute("SELECT COUNT(*) FROM chatter").fetchone()[0]
        signals = self._conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        by_source = {
            row["source"]: row["n"]
            for row in self._conn.execute(
                "SELECT source, COUNT(*) AS n FROM chatter GROUP BY source"
            )
        }
        return {
            "chatter": chatter,
            "signals": signals,
            **{f"source:{k}": v for k, v in by_source.items()},
        }

    @staticmethod
    def _item_from_row(row: sqlite3.Row) -> ChatterItem:
        published = row["published_at"]
        collected = row["collected_at"]
        extra = json.loads(row["extra_json"] or "{}")
        return ChatterItem(
            id=row["id"],
            source=row["source"],
            url=row["url"],
            title=row["title"] or "",
            body=row["body"] or "",
            author=row["author"],
            published_at=datetime.fromisoformat(published) if published else None,
            collected_at=datetime.fromisoformat(collected),
            query=row["query"] or "",
            extra=extra,
        )

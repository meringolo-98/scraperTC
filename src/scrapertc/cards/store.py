from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from scrapertc.cards.models import CardListing, GradeReport, StealHit

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    body TEXT,
    price_usd REAL,
    currency TEXT,
    image_urls_json TEXT,
    seller TEXT,
    condition TEXT,
    query TEXT,
    collected_at TEXT NOT NULL,
    first_seen TEXT,
    last_seen TEXT,
    hit_count INTEGER DEFAULT 1,
    extra_json TEXT
);

CREATE TABLE IF NOT EXISTS grades (
    listing_id TEXT PRIMARY KEY,
    image_url TEXT,
    centering_lr REAL,
    centering_tb REAL,
    whitening_edge_pct REAL,
    corner_wear_score REAL,
    defects_json TEXT,
    grade_band TEXT,
    notes TEXT,
    analyzed_at TEXT,
    FOREIGN KEY (listing_id) REFERENCES listings(id)
);

CREATE TABLE IF NOT EXISTS steals (
    listing_id TEXT PRIMARY KEY,
    score REAL,
    listed_as TEXT,
    suspected TEXT,
    reasons_json TEXT,
    listed_price REAL,
    reference_floor REAL,
    detected_at TEXT,
    FOREIGN KEY (listing_id) REFERENCES listings(id)
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gate TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    stats_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_listings_source ON listings(source);
CREATE INDEX IF NOT EXISTS idx_steals_score ON steals(score);
"""


class CardStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert_listings(self, items: Iterable[CardListing]) -> dict[str, int]:
        new = 0
        updated = 0
        for item in items:
            seen = item.collected_at.isoformat()
            extra = json.dumps(item.extra)
            images = json.dumps(item.image_urls)
            existing = self._conn.execute(
                "SELECT id FROM listings WHERE id = ?", (item.id,)
            ).fetchone()
            if existing:
                self._conn.execute(
                    """
                    UPDATE listings SET
                        title = ?, body = ?, price_usd = COALESCE(?, price_usd),
                        currency = ?, image_urls_json = ?, seller = COALESCE(?, seller),
                        condition = COALESCE(?, condition), last_seen = ?,
                        hit_count = COALESCE(hit_count, 1) + 1, extra_json = ?
                    WHERE id = ?
                    """,
                    (
                        item.title,
                        item.body,
                        item.price_usd,
                        item.currency,
                        images,
                        item.seller,
                        item.condition,
                        seen,
                        extra,
                        item.id,
                    ),
                )
                updated += 1
            else:
                self._conn.execute(
                    """
                    INSERT INTO listings (
                        id, source, url, title, body, price_usd, currency,
                        image_urls_json, seller, condition, query, collected_at,
                        first_seen, last_seen, hit_count, extra_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        item.id,
                        item.source,
                        item.url,
                        item.title,
                        item.body,
                        item.price_usd,
                        item.currency,
                        images,
                        item.seller,
                        item.condition,
                        item.query,
                        seen,
                        seen,
                        seen,
                        extra,
                    ),
                )
                new += 1
        self._conn.commit()
        return {"new": new, "updated": updated, "written": new + updated}

    def upsert_grades(self, reports: Iterable[GradeReport]) -> int:
        count = 0
        for report in reports:
            row = report.as_row()
            self._conn.execute(
                """
                INSERT INTO grades (
                    listing_id, image_url, centering_lr, centering_tb,
                    whitening_edge_pct, corner_wear_score, defects_json,
                    grade_band, notes, analyzed_at
                ) VALUES (
                    :listing_id, :image_url, :centering_lr, :centering_tb,
                    :whitening_edge_pct, :corner_wear_score, :defects_json,
                    :grade_band, :notes, :analyzed_at
                )
                ON CONFLICT(listing_id) DO UPDATE SET
                    image_url=excluded.image_url,
                    centering_lr=excluded.centering_lr,
                    centering_tb=excluded.centering_tb,
                    whitening_edge_pct=excluded.whitening_edge_pct,
                    corner_wear_score=excluded.corner_wear_score,
                    defects_json=excluded.defects_json,
                    grade_band=excluded.grade_band,
                    notes=excluded.notes,
                    analyzed_at=excluded.analyzed_at
                """,
                row,
            )
            count += 1
        self._conn.commit()
        return count

    def upsert_steals(self, hits: Iterable[StealHit]) -> int:
        count = 0
        for hit in hits:
            row = hit.as_row()
            self._conn.execute(
                """
                INSERT INTO steals (
                    listing_id, score, listed_as, suspected, reasons_json,
                    listed_price, reference_floor, detected_at
                ) VALUES (
                    :listing_id, :score, :listed_as, :suspected, :reasons_json,
                    :listed_price, :reference_floor, :detected_at
                )
                ON CONFLICT(listing_id) DO UPDATE SET
                    score=excluded.score,
                    listed_as=excluded.listed_as,
                    suspected=excluded.suspected,
                    reasons_json=excluded.reasons_json,
                    listed_price=excluded.listed_price,
                    reference_floor=excluded.reference_floor,
                    detected_at=excluded.detected_at
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
            (gate, started_at.isoformat(), finished.isoformat(), json.dumps(stats)),
        )
        self._conn.commit()

    def all_listings(self) -> list[CardListing]:
        rows = self._conn.execute("SELECT * FROM listings ORDER BY collected_at DESC").fetchall()
        return [self._listing_from_row(row) for row in rows]

    def steal_rows(self, *, min_score: float = 0.0) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT l.*, s.score, s.listed_as, s.suspected, s.reasons_json,
                   s.listed_price, s.reference_floor, s.detected_at AS steal_detected_at,
                   g.grade_band, g.defects_json, g.centering_lr, g.centering_tb,
                   g.whitening_edge_pct
            FROM steals s
            JOIN listings l ON l.id = s.listing_id
            LEFT JOIN grades g ON g.listing_id = l.id
            WHERE s.score >= ?
            ORDER BY s.score DESC, l.collected_at DESC
            """,
            (min_score,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data["reasons"] = json.loads(data.pop("reasons_json") or "[]")
            data["defects"] = json.loads(data.pop("defects_json") or "[]")
            data["image_urls"] = json.loads(data.pop("image_urls_json") or "[]")
            data["extra"] = json.loads(data.pop("extra_json") or "{}")
            out.append(data)
        return out

    def enriched_rows(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT l.*, g.grade_band, g.defects_json, g.centering_lr, g.centering_tb,
                   g.whitening_edge_pct, g.corner_wear_score, g.notes AS grade_notes,
                   s.score AS steal_score, s.listed_as, s.suspected, s.reasons_json,
                   s.reference_floor
            FROM listings l
            LEFT JOIN grades g ON g.listing_id = l.id
            LEFT JOIN steals s ON s.listing_id = l.id
            ORDER BY COALESCE(s.score, 0) DESC, l.collected_at DESC
            """
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data["defects"] = json.loads(data.pop("defects_json") or "[]")
            data["reasons"] = json.loads(data.pop("reasons_json") or "[]")
            data["image_urls"] = json.loads(data.pop("image_urls_json") or "[]")
            data["extra"] = json.loads(data.pop("extra_json") or "{}")
            out.append(data)
        return out

    def export_jsonl(self, path: Path, *, steals_only: bool = False) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = self.steal_rows() if steals_only else self.enriched_rows()
        n = 0
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                n += 1
        return n

    def counts(self) -> dict[str, int]:
        listings = self._conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        grades = self._conn.execute("SELECT COUNT(*) FROM grades").fetchone()[0]
        steals = self._conn.execute("SELECT COUNT(*) FROM steals").fetchone()[0]
        by_source = {
            row["source"]: row["n"]
            for row in self._conn.execute(
                "SELECT source, COUNT(*) AS n FROM listings GROUP BY source"
            )
        }
        return {
            "listings": listings,
            "grades": grades,
            "steals": steals,
            **{f"source:{k}": v for k, v in by_source.items()},
        }

    @staticmethod
    def _listing_from_row(row: sqlite3.Row) -> CardListing:
        return CardListing(
            id=row["id"],
            source=row["source"],
            url=row["url"],
            title=row["title"] or "",
            body=row["body"] or "",
            price_usd=row["price_usd"],
            currency=row["currency"] or "USD",
            image_urls=json.loads(row["image_urls_json"] or "[]"),
            seller=row["seller"],
            condition=row["condition"],
            query=row["query"] or "",
            collected_at=datetime.fromisoformat(row["collected_at"]),
            extra=json.loads(row["extra_json"] or "{}"),
        )

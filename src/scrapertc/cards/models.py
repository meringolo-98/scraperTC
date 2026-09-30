from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from scrapertc.models import canonicalize_url, squeeze


def utcnow() -> datetime:
    return datetime.now(UTC)


def make_listing_id(source: str, url: str, fallback: str = "") -> str:
    key = f"card|{source}|{canonicalize_url(url) or fallback}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


_PRICE = re.compile(
    r"(?i)(?:\$|usd\s*)(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)"
)


def parse_price_usd(text: str | None) -> float | None:
    if not text:
        return None
    match = _PRICE.search(text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


class CardListing(BaseModel):
    id: str
    source: str
    url: str
    title: str = ""
    body: str = ""
    price_usd: float | None = None
    currency: str = "USD"
    image_urls: list[str] = Field(default_factory=list)
    seller: str | None = None
    condition: str | None = None
    query: str = ""
    collected_at: datetime = Field(default_factory=utcnow)
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def text(self) -> str:
        return squeeze(f"{self.title} {self.body}")


class GradeReport(BaseModel):
    listing_id: str
    image_url: str = ""
    centering_lr: float | None = None  # left share of LR borders, 0-100
    centering_tb: float | None = None
    whitening_edge_pct: float | None = None
    corner_wear_score: float | None = None
    defects: list[str] = Field(default_factory=list)
    grade_band: str = "unknown"  # gem / near_mint / played / damaged / unknown
    notes: str = ""
    analyzed_at: datetime = Field(default_factory=utcnow)

    def as_row(self) -> dict[str, Any]:
        return {
            "listing_id": self.listing_id,
            "image_url": self.image_url,
            "centering_lr": self.centering_lr,
            "centering_tb": self.centering_tb,
            "whitening_edge_pct": self.whitening_edge_pct,
            "corner_wear_score": self.corner_wear_score,
            "defects_json": json.dumps(self.defects),
            "grade_band": self.grade_band,
            "notes": self.notes,
            "analyzed_at": self.analyzed_at.isoformat(),
        }


class StealHit(BaseModel):
    listing_id: str
    score: float = 0.0
    listed_as: str = ""
    suspected: str = ""
    reasons: list[str] = Field(default_factory=list)
    listed_price: float | None = None
    reference_floor: float | None = None
    detected_at: datetime = Field(default_factory=utcnow)

    def as_row(self) -> dict[str, Any]:
        return {
            "listing_id": self.listing_id,
            "score": self.score,
            "listed_as": self.listed_as,
            "suspected": self.suspected,
            "reasons_json": json.dumps(self.reasons),
            "listed_price": self.listed_price,
            "reference_floor": self.reference_floor,
            "detected_at": self.detected_at.isoformat(),
        }

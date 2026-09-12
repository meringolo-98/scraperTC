from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import BaseModel, Field

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def canonicalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    host = parsed.netloc.lower().removeprefix("www.")
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower() or "https", host, path, "", urlencode(query), ""))


def make_item_id(source: str, url: str, fallback: str = "") -> str:
    key = f"{source}|{canonicalize_url(url) or fallback}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


_WHITESPACE = re.compile(r"\s+")


def squeeze(text: str | None) -> str:
    return _WHITESPACE.sub(" ", (text or "").strip())


class ChatterItem(BaseModel):
    id: str
    source: str
    url: str
    title: str = ""
    body: str = ""
    author: str | None = None
    published_at: datetime | None = None
    collected_at: datetime = Field(default_factory=utcnow)
    query: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def text(self) -> str:
        return squeeze(f"{self.title} {self.body}")


class Signal(BaseModel):
    item_id: str
    domain: str = "unknown"
    competition: float = 0.0
    breakthrough: float = 0.0
    saturation: float = 0.0
    relevance: float = 0.0
    labels: list[str] = Field(default_factory=list)
    segments: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    rationale: str = ""
    classified_at: datetime = Field(default_factory=utcnow)

    def as_row(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "domain": self.domain,
            "competition": self.competition,
            "breakthrough": self.breakthrough,
            "saturation": self.saturation,
            "relevance": self.relevance,
            "labels_json": json.dumps(self.labels),
            "segments_json": json.dumps(self.segments),
            "entities_json": json.dumps(self.entities),
            "rationale": self.rationale,
            "classified_at": self.classified_at.isoformat(),
        }


class RunStats(BaseModel):
    gate: str
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

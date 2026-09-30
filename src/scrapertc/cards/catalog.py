from __future__ import annotations

import re
from typing import Any

from scrapertc.cards.config import normalize, steal_config

CONDITION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("sealed", re.compile(r"\b(sealed|new\s*in\s*package|nip)\b", re.I)),
    ("gem", re.compile(r"\b(psa\s*10|bgs\s*10|cgc\s*10|gem\s*mint)\b", re.I)),
    ("near_mint", re.compile(r"\b(near\s*mint|\bnm\b|mint)\b", re.I)),
    ("lightly_played", re.compile(r"\b(lightly\s*played|\blp\b)\b", re.I)),
    ("moderately_played", re.compile(r"\b(moderately\s*played|\bmp\b)\b", re.I)),
    ("heavily_played", re.compile(r"\b(heavily\s*played|\bhp\b)\b", re.I)),
    ("damaged", re.compile(r"\b(damaged|\bdmg\b|creased|bent)\b", re.I)),
]

EDITION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("1st edition", re.compile(r"\b(1st\s*edition|first\s*edition|1st\s*ed\.?)\b", re.I)),
    ("shadowless", re.compile(r"\bshadow\s*-?less\b", re.I)),
    ("unlimited", re.compile(r"\bunlimited\b", re.I)),
]


def infer_condition(text: str) -> str | None:
    for label, pattern in CONDITION_PATTERNS:
        if pattern.search(text or ""):
            return label
    return None


def detect_markers(text: str) -> list[str]:
    found: list[str] = []
    lowered = normalize(text or "")
    for label, pattern in EDITION_PATTERNS:
        if pattern.search(text or ""):
            found.append(label)
    cfg = steal_config()
    for marker in cfg.get("valuable_markers") or []:
        m = normalize(str(marker))
        if m and m in lowered and m not in found:
            found.append(str(marker))
    return found


def listed_as_summary(text: str) -> str:
    markers = detect_markers(text)
    if markers:
        return ", ".join(markers)
    lowered = normalize(text)
    if "base" in lowered:
        return "base / unspecified edition"
    return "unspecified"


def match_high_value_card(text: str) -> dict[str, Any] | None:
    lowered = normalize(text)
    for card in steal_config().get("high_value_cards") or []:
        name = normalize(str(card.get("name") or ""))
        number = normalize(str(card.get("number") or ""))
        set_name = normalize(str(card.get("set") or ""))
        if not name:
            continue
        name_hit = name in lowered
        number_hit = bool(number) and (
            number in lowered or number.split("/")[0] in lowered.split()
        )
        set_hit = bool(set_name) and set_name in lowered
        if name_hit and (number_hit or set_hit):
            return dict(card)
    return None


def suspected_variant(text: str, card: dict[str, Any] | None = None) -> str | None:
    markers = detect_markers(text)
    for preferred in ("1st edition", "shadowless", "unlimited"):
        if preferred in markers or any(preferred in m for m in markers):
            return preferred
    # Stamp / cue words that sellers forget to put in the title taxonomy.
    cues = [
        ("1st edition", re.compile(r"\b(1st\s*edition\s*stamp|set\s*symbol.*1st)\b", re.I)),
        ("shadowless", re.compile(r"\b(no\s*shadow|shadowless\s*print)\b", re.I)),
    ]
    for label, pattern in cues:
        if pattern.search(text or ""):
            return label
    if card:
        for marker in card.get("markers") or []:
            if normalize(str(marker)) in normalize(text):
                return str(marker)
    return None

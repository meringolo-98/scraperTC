"""Steal detector — listings that understate a valuable variant.

Example: 1st-edition Charizard cues / stamp language / price floors while the
title only says "base set Charizard".
"""

from __future__ import annotations

from scrapertc.cards.catalog import (
    detect_markers,
    listed_as_summary,
    match_high_value_card,
    suspected_variant,
)
from scrapertc.cards.config import normalize, steal_config
from scrapertc.cards.models import CardListing, StealHit


def score_steal(listing: CardListing) -> StealHit | None:
    if listing.extra.get("catalog"):
        return None
    # Market comps / search deep-links aren't seller mislistings.
    if listing.condition in {"market", "search", "reference"}:
        return None
    if listing.extra.get("engine") in {"pricecharting", "live_search"}:
        return None
    cfg = steal_config()
    text = listing.text
    card = match_high_value_card(text)
    markers = detect_markers(text)
    listed = listed_as_summary(text)
    suspected = suspected_variant(text, card)
    reasons: list[str] = []
    score = 0.0
    listed_price = listing.price_usd
    reference_floor: float | None = None

    understate = [normalize(str(p)) for p in (cfg.get("understate_phrases") or [])]
    valuable = [normalize(str(m)) for m in (cfg.get("valuable_markers") or [])]
    lowered = normalize(text)

    title_understates = any(p in normalize(listing.title) for p in understate) or (
        "1st" not in normalize(listing.title) and "shadowless" not in normalize(listing.title)
    )
    body_or_extra_valuable = any(v in lowered for v in valuable)

    title_markers = detect_markers(listing.title)
    title_already_discloses = bool(title_markers)
    if card and title_understates and body_or_extra_valuable and not title_already_discloses:
        # Title looks like plain base, but valuable markers appear somewhere else.
        other_markers = [m for m in markers if m not in title_markers]
        if other_markers or (suspected and suspected not in title_markers):
            score += 0.45
            reasons.append(
                "title understates edition; valuable marker elsewhere: "
                + ", ".join(other_markers or [suspected or "unknown"])
            )
            suspected = suspected or (other_markers[0] if other_markers else None)

    if card and suspected:
        floors = card.get("floor_usd") or {}
        floor_key = suspected if suspected in floors else None
        if floor_key is None:
            for key in floors:
                if normalize(key) in normalize(suspected):
                    floor_key = key
                    break
        if floor_key is not None:
            reference_floor = float(floors[floor_key])
            gap_ratio = float(cfg.get("price_gap_ratio") or 2.5)
            if listed_price is not None and listed_price > 0:
                if reference_floor / listed_price >= gap_ratio:
                    score += 0.4
                    reasons.append(
                        f"price ${listed_price:.0f} << {suspected} floor ${reference_floor:.0f}"
                    )
            else:
                score += 0.15
                reasons.append(f"no price; {suspected} floor ${reference_floor:.0f}")

    # Explicit mismatch phrases: "base" title + "1st edition" in body.
    if (
        not title_already_discloses
        and re_search_base_title(listing.title)
        and any("1st" in normalize(m) or "first" in normalize(m) for m in markers)
        and "1st" not in normalize(listing.title)
        and "first" not in normalize(listing.title)
    ):
        score += 0.35
        reasons.append("listed as base/unlimited tone but 1st-edition marker present")
        suspected = suspected or "1st edition"

    if (
        card is None
        and not title_already_discloses
        and body_or_extra_valuable
        and title_understates
        and listing.price_usd
    ):
        # Generic steal cue without catalog match — weaker.
        score += 0.2
        reasons.append("valuable marker with understated title")

    min_score = float(cfg.get("min_score") or 0.55)
    if score < min_score or not reasons:
        return None

    return StealHit(
        listing_id=listing.id,
        score=round(min(score, 1.0), 3),
        listed_as=listed,
        suspected=suspected or "higher-value variant",
        reasons=reasons,
        listed_price=listed_price,
        reference_floor=reference_floor,
    )


def find_steals(listings: list[CardListing]) -> list[StealHit]:
    hits: list[StealHit] = []
    for listing in listings:
        hit = score_steal(listing)
        if hit is not None:
            hits.append(hit)
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits


def re_search_base_title(title: str) -> bool:
    t = normalize(title)
    return "base" in t or "unlimited" in t or (
        "charizard" in t and "1st" not in t and "shadowless" not in t
    )

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from scrapertc.cards.catalog import detect_markers, match_high_value_card
from scrapertc.cards.collectors import listing
from scrapertc.cards.config import budget_cap, build_queries
from scrapertc.cards.demo import demo_card_listings
from scrapertc.cards.pipeline import collect_cards, detect_steals, run_cards
from scrapertc.cards.steal import score_steal
from scrapertc.cards.store import CardStore
from scrapertc.cards.vision import analyze_listing_image
from scrapertc.settings import Settings, get_settings


@pytest.fixture
def card_store(tmp_path) -> CardStore:
    return CardStore(tmp_path / "cards.db")


@pytest.fixture
def card_settings(tmp_path) -> Settings:
    get_settings.cache_clear()
    return Settings(
        scrapertc_db=str(tmp_path / "chatter.db"),
        scrapertc_cards_db=str(tmp_path / "cards.db"),
        contact_email="test@example.com",
    )


def test_budget_cap_shares_gate1_limit():
    # default_limit 40 * 0.25 share = 10, cards default_limit 20 → min = 10
    assert budget_cap(40) == 10
    assert budget_cap(40, override=3) == 3


def test_build_queries_from_watchlist():
    queries = build_queries()
    assert any("Charizard" in q for q in queries)
    assert build_queries("Pikachu Jungle") == ["Pikachu Jungle"]


def test_steal_flags_underlisted_1st_edition():
    item = listing(
        source="ebay",
        url="https://www.ebay.com/itm/steal-charizard",
        title="Pokemon Base Set Charizard Holo 4/102",
        body="Has the 1st edition stamp. Sold as binder copy.",
        price_usd=200,
    )
    assert match_high_value_card(item.text) is not None
    assert any("1st" in m for m in detect_markers(item.body))
    hit = score_steal(item)
    assert hit is not None
    assert hit.score >= 0.55
    assert "1st" in hit.suspected or "edition" in hit.suspected


def test_steal_ignores_fair_shadowless_price():
    item = listing(
        source="tcgplayer",
        url="https://www.tcgplayer.com/product/fair-blastoise",
        title="Blastoise Base Set Shadowless Holo 2/102",
        body="Shadowless LP",
        price_usd=320,
    )
    hit = score_steal(item)
    # Title already discloses shadowless — not a mislisting steal.
    assert hit is None or hit.score < 0.55 or "understates" not in " ".join(hit.reasons)


def test_vision_detects_off_center_and_whitening():
    # Heavy left margin, thin right; bright white edges.
    image = Image.new("RGB", (200, 280), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 20, 190, 260), fill=(30, 90, 40))  # artwork shifted right
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    item = listing(
        source="ebay",
        url="https://example.com/card-photo",
        title="Test card",
        body="",
    )
    report = analyze_listing_image(item, image_bytes=buf.getvalue(), image_url="mem://test")
    assert report.centering_lr is not None
    assert report.whitening_edge_pct is not None
    assert report.whitening_edge_pct > 0
    assert report.grade_band in {"gem", "near_mint", "played", "unknown"}


def test_demo_pipeline_collect_and_steals(card_settings: Settings, card_store: CardStore):
    stats = collect_cards(settings=card_settings, store=card_store, items=demo_card_listings())
    assert stats["collected"] >= 4
    assert stats["new"] >= 4
    steal_stats = detect_steals(settings=card_settings, store=card_store)
    assert steal_stats["candidates"] >= 1
    rows = card_store.steal_rows()
    assert any("Charizard" in (r.get("title") or "") for r in rows)


def test_run_cards_demo(card_settings: Settings, tmp_path, monkeypatch):
    monkeypatch.setenv("SCRAPERTC_CARDS_DB", str(tmp_path / "cards.db"))
    get_settings.cache_clear()
    result = run_cards(settings=card_settings, items=demo_card_listings(), skip_vision=True)
    assert result["collect"]["upserted"] >= 4  # type: ignore[index]
    assert result["steals"]["candidates"] >= 1  # type: ignore[index]
    assert "html" in result["report"]

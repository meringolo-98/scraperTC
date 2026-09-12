from __future__ import annotations

from scrapertc.demo import demo_items
from scrapertc.gate2 import classify


def test_demo_items_cover_all_three_gates() -> None:
    labels = {item.id: classify(item) for item in demo_items()}
    all_labels = {label for signal in labels.values() for label in signal.labels}
    assert "competition" in all_labels
    assert "breakthrough" in all_labels
    assert "saturation" in all_labels


def test_competition_hits_known_vendor() -> None:
    item = next(i for i in demo_items() if "Plant Cell Technology" in i.title)
    signal = classify(item)
    assert signal.domain == "plant"
    assert "competition" in signal.labels
    assert "Plant Cell Technology" in signal.entities
    assert signal.competition >= 0.34


def test_breakthrough_scientific_protocol() -> None:
    item = next(i for i in demo_items() if i.source == "pubmed")
    signal = classify(item)
    assert signal.domain == "plant"
    assert "breakthrough" in signal.labels
    assert signal.breakthrough >= 0.34


def test_saturation_market_flood() -> None:
    item = next(i for i in demo_items() if i.source == "reddit")
    signal = classify(item)
    assert "saturation" in signal.labels
    assert signal.saturation >= 0.34


def test_mammalian_tagged_off_domain() -> None:
    item = next(i for i in demo_items() if i.source == "openalex")
    signal = classify(item)
    assert signal.domain == "mammalian"
    assert "off-domain" in signal.labels
    assert "breakthrough" not in signal.labels


def test_explant_is_not_xplant() -> None:
    item = next(i for i in demo_items() if i.source == "youtube")
    signal = classify(item)
    assert "Xplant" not in signal.entities

from __future__ import annotations

from scrapertc.demo import demo_items
from scrapertc.gate2 import classify
from scrapertc.settings import search_queries


def test_search_budget_is_cannabis_first() -> None:
    queries = search_queries()
    assert queries[0].lower().startswith("cannabis")
    blob = " ".join(queries).lower()
    assert "genomic" in blob
    assert "hop latent" in blob or "hlvd" in blob


def test_demo_items_cover_all_three_gates() -> None:
    labels = {item.id: classify(item) for item in demo_items()}
    all_labels = {label for signal in labels.values() for label in signal.labels}
    assert "competition" in all_labels
    assert "breakthrough" in all_labels
    assert "saturation" in all_labels


def test_cannabis_tc_lab_is_competition() -> None:
    item = next(i for i in demo_items() if "Segra International" in i.title)
    signal = classify(item)
    assert signal.domain == "cannabis"
    assert "cannabis_tc" in signal.segments
    assert "remediation" in signal.segments
    assert "competition" in signal.labels
    assert "Segra International" in signal.entities
    assert signal.competition >= 0.34
    assert signal.relevance >= 0.5


def test_genomic_prediction_for_breeders() -> None:
    item = next(i for i in demo_items() if "New West Genetics" in i.title)
    signal = classify(item)
    assert signal.domain == "cannabis"
    assert "genomic_prediction" in signal.segments
    assert "competition" in signal.labels
    assert "New West Genetics" in signal.entities


def test_hlvd_meristem_is_breakthrough() -> None:
    item = next(i for i in demo_items() if i.source == "pubmed")
    signal = classify(item)
    assert signal.domain == "cannabis"
    assert "breakthrough" in signal.labels
    assert signal.breakthrough >= 0.34
    assert "hop latent viroid" in signal.entities or "HLVd" in item.text


def test_saturation_market_flood() -> None:
    item = next(i for i in demo_items() if i.source == "reddit")
    signal = classify(item)
    assert "saturation" in signal.labels
    assert signal.saturation >= 0.34
    assert signal.domain == "cannabis"


def test_mammalian_tagged_off_domain() -> None:
    item = next(i for i in demo_items() if i.source == "openalex")
    signal = classify(item)
    assert signal.domain == "mammalian"
    assert "off-domain" in signal.labels
    assert "breakthrough" not in signal.labels
    assert signal.relevance < 0.2


def test_explant_is_not_xplant() -> None:
    item = next(i for i in demo_items() if i.source == "youtube")
    signal = classify(item)
    assert "Xplant" not in signal.entities
    assert "competition" not in signal.labels
    assert signal.relevance < 0.4


def test_cannabis_tech_breakthrough() -> None:
    item = next(i for i in demo_items() if i.source == "web")
    signal = classify(item)
    assert "cannabis_tech" in signal.segments or "genomic_prediction" in signal.segments
    assert "breakthrough" in signal.labels
    assert "Medicinal Genomics" in signal.entities


def test_generic_crop_microprop_is_not_cannabis() -> None:
    from scrapertc.collectors import item as make_item

    row = make_item(
        source="openalex",
        url="https://example.com/pepper-tc",
        title="Genetic fidelity of micropropagated pepper",
        body="Piper nigrum plantlets of cultivar Semongok using ISSR markers in vitro.",
    )
    signal = classify(row)
    assert signal.domain != "cannabis"
    assert "cannabis_tc" not in signal.segments

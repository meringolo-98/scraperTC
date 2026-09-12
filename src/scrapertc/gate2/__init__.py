from __future__ import annotations

import re

from scrapertc.models import ChatterItem, Signal
from scrapertc.settings import competitors_config

PLANT_TERMS = (
    "plant",
    "micropropagation",
    "explant",
    "meristem",
    "orchid",
    "banana",
    "agar",
    "murashige",
    "ms medium",
    "cytokinin",
    "auxin",
    "iba",
    "bap",
    "ppm",
    "flask",
    "laminar",
    "hood",
    "sterile",
    "tc plant",
    "mericlone",
    "somatic embryogenesis",
    "bioreactor",
    "nursery",
    "propagation",
    "in vitro",
    "callus",
    "acclimatization",
    "hardening",
)

MAMMALIAN_TERMS = (
    "hela",
    "hek293",
    "cho cell",
    "ipsc",
    "ips cell",
    "organoid",
    "mammalian",
    "stem cell",
    "cell therapy",
    "bioreactor cell",
    "tissue engineering",
    "scaffold",
    "in vivo",
    "patient",
    "clinical trial",
    "oncology",
    "fibroblast",
)

COMPETITION_PHRASES = (
    "we launched",
    "now shipping",
    "now offering",
    "in stock",
    "preorder",
    "pre-order",
    "wholesale",
    "our lab",
    "our facility",
    "hiring",
    "we're hiring",
    "price list",
    "catalog",
    "sku",
    "buy now",
    "shop now",
    "order now",
    "new product",
    "product launch",
    "raised funding",
    "series a",
    "opened a lab",
    "expansion",
    "partnership",
    "distributor",
    "commercial scale",
    "available from",
)

BREAKTHROUGH_PHRASES = (
    "first report",
    "we report",
    "novel protocol",
    "new protocol",
    "patent",
    "published",
    "preprint",
    "breakthrough",
    "contamination rate",
    "multiplication rate",
    "yield increase",
    "crispr",
    "genome edit",
    "automation",
    "robotic",
    "temporary immersion",
    "somatic embryogenesis",
    "protocol optimized",
    "significantly improved",
    "higher survival",
    "reduced contamination",
    "open source protocol",
    "peer-reviewed",
    "doi:",
)

SATURATION_PHRASES = (
    "saturated",
    "saturation",
    "flooded",
    "too many",
    "everyone is doing",
    "race to the bottom",
    "price war",
    "commodit",
    "crowded market",
    "another tc",
    "another tissue culture",
    "oversupply",
    "too cheap",
    "hobbyist boom",
    "barrier to entry is low",
    "everyone and their",
    "market is full",
    "nothing new",
    "same protocol",
)

LABEL_THRESHOLD = 0.34


def classify(item: ChatterItem) -> Signal:
    text = item.text.lower()
    domain = _domain(text)
    entities = _entities(text, item)
    competition = _score(text, COMPETITION_PHRASES, extra=0.28 if entities else 0.0)
    if item.source in {"linkedin", "web", "youtube"} and entities:
        competition = min(1.0, competition + 0.12)
    if any(word in text for word in ("lab", "nursery", "company", "brand", "startup")):
        competition = min(1.0, competition + 0.1)

    breakthrough = _score(text, BREAKTHROUGH_PHRASES)
    if item.source in {"pubmed", "openalex", "arxiv", "patent"} and domain == "plant":
        breakthrough = min(1.0, breakthrough + 0.35)
    if "protocol" in text or "medium formulation" in text:
        breakthrough = min(1.0, breakthrough + 0.08)

    saturation = _score(text, SATURATION_PHRASES)
    if text.count("buy") + text.count("for sale") >= 3:
        saturation = min(1.0, saturation + 0.15)

    labels = []
    if competition >= LABEL_THRESHOLD:
        labels.append("competition")
    if breakthrough >= LABEL_THRESHOLD:
        labels.append("breakthrough")
    if saturation >= LABEL_THRESHOLD:
        labels.append("saturation")
    if domain == "mammalian" and "plant" not in text:
        # still keep the row, but tag it so Gate 2 can ignore it for plant-comp work
        labels.append("off-domain")

    rationale_bits = [f"domain={domain}"]
    if entities:
        rationale_bits.append("entities=" + ", ".join(entities[:6]))
    rationale_bits.append(
        f"scores c={competition:.2f} b={breakthrough:.2f} s={saturation:.2f}"
    )

    return Signal(
        item_id=item.id,
        domain=domain,
        competition=round(competition, 3),
        breakthrough=round(breakthrough, 3),
        saturation=round(saturation, 3),
        labels=labels,
        entities=entities,
        rationale="; ".join(rationale_bits),
    )


def _domain(text: str) -> str:
    plant = sum(1 for term in PLANT_TERMS if term in text)
    mammalian = sum(1 for term in MAMMALIAN_TERMS if term in text)
    if plant and mammalian:
        return "mixed"
    if plant:
        return "plant"
    if mammalian:
        return "mammalian"
    if "tissue culture" in text or "micropropagation" in text:
        return "plant" if "micropropagation" in text else "unknown"
    return "unknown"


def _entities(text: str, item: ChatterItem) -> list[str]:
    cfg = competitors_config()
    names = [str(n) for n in (cfg.get("companies") or [])]
    aliases = {str(k).lower(): str(v) for k, v in (cfg.get("aliases") or {}).items()}
    found: list[str] = []
    extra_labs = item.extra.get("labs") if item.extra else None
    lab_text = " ".join(str(x) for x in extra_labs) if isinstance(extra_labs, list) else ""
    blob = f"{text} {item.author or ''} {lab_text}"
    blob_l = blob.lower()
    for name in names:
        if _whole_phrase(name.lower(), blob_l):
            found.append(name)
    for alias, canonical in aliases.items():
        if re.search(rf"\b{re.escape(alias)}\b", blob_l) and canonical not in found:
            found.append(canonical)
    labs = item.extra.get("labs") if item.extra else None
    if isinstance(labs, list):
        for lab in labs[:5]:
            if lab not in found:
                found.append(str(lab))
    return found


def _whole_phrase(phrase: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def _score(text: str, phrases: tuple[str, ...], extra: float = 0.0) -> float:
    hits = sum(1 for phrase in phrases if phrase in text)
    if hits == 0 and extra == 0:
        return 0.0
    base = min(1.0, 0.22 * hits + extra)
    return min(1.0, base)

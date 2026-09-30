from __future__ import annotations

import re

from scrapertc.models import ChatterItem, Signal
from scrapertc.settings import competitors_config

CANNABIS_TERMS = (
    "cannabis",
    "marijuana",
    "hemp",
    "cannabinoid",
    "thca",
    "cbda",
    "hlvd",
    "hop latent",
    "chemovar",
    "phenohunt",
    "pheno hunt",
    "clone-only",
)

TC_TERMS = (
    "tissue culture",
    "micropropagation",
    "explant",
    "meristem",
    "mericlone",
    "in vitro",
    "callus",
    "ms medium",
    "murashige",
    "laminar",
    "flask",
    "ppm",
    "somatic embryogenesis",
    "temporary immersion",
    "clean stock",
    "virus-free",
    "viroid-free",
    "remediation",
    "acclimatization",
)

GENOMIC_TERMS = (
    "genomic selection",
    "genomic prediction",
    "gblup",
    "gwas",
    "marker-assisted",
    "snp",
    "genotype",
    "whole genome",
    "haplotype",
    "polygenic",
    "breeding value",
    "gebv",
    "chemotype prediction",
    "predictive breeding",
    "genomic estimated",
    "qtls",
    "qtl ",
)

TECH_TERMS = (
    "crispr",
    "genome edit",
    "phenotyping",
    "hyperspectral",
    "computer vision",
    "automation",
    "robotic",
    "pathogen panel",
    "qpcr",
    "sequencing",
    "bioinformatics",
    "machine learning",
    "ai breeding",
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
    "tissue engineering",
    "scaffold",
    "clinical trial",
    "oncology",
    "fibroblast",
)

HOBBY_NOISE = (
    "orchid flask",
    "banana plantlet",
    "etsy",
    "kitchen tissue culture",
    "aquarium",
    "planted tank",
)

COMPETITION_PHRASES = (
    "we launched",
    "now shipping",
    "now offering",
    "in stock",
    "wholesale",
    "our lab",
    "our facility",
    "hiring",
    "we're hiring",
    "price list",
    "catalog",
    "new product",
    "product launch",
    "raised funding",
    "series a",
    "opened a lab",
    "expansion",
    "partnership",
    "commercial scale",
    "available from",
    "clean stock",
    "virus-free",
    "viroid-free",
    "meristem service",
    "tissue culture service",
    "now offering genomic",
    "breeding panel",
    "snp panel",
    "for breeders",
    "licensed nursery",
    "white label tc",
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
    "peer-reviewed",
    "doi:",
    "viroid elimination",
    "meristem tip",
    "hop latent",
    "genomic selection",
    "genomic prediction",
    "marker-assisted",
    "whole genome",
    "chemotype prediction",
    "haploid",
    "ploidy",
    "somaclonal",
    "pathogen-free",
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
    "market is full",
    "nothing new",
    "same protocol",
    "every nursery",
    "another clean stock",
    "sex test commodit",
    "everyone offers hlvd",
)

LABEL_THRESHOLD = 0.34
RELEVANCE_THRESHOLD = 0.4


def classify(item: ChatterItem) -> Signal:
    text = item.text.lower()
    domain = _domain(text)
    segments = _segments(text, domain)
    entities = _entities(text, item)

    cannabis = domain == "cannabis"
    on_mission = bool(
        set(segments)
        & {"cannabis_tc", "remediation", "tc_company", "genomic_prediction", "cannabis_tech"}
    )

    # A named player is already a lead. Extra pushes them over LABEL_THRESHOLD.
    competition = _score(text, COMPETITION_PHRASES, extra=0.36 if entities else 0.0)
    if item.source in {"linkedin", "web", "youtube"} and entities:
        competition = min(1.0, competition + 0.12)
    if any(
        _whole_phrase(word, text)
        for word in ("lab", "nursery", "company", "brand", "startup", "breeder")
    ):
        competition = min(1.0, competition + 0.1)
    if cannabis and entities:
        competition = min(1.0, competition + 0.12)
    if any(noise in text for noise in HOBBY_NOISE) and not cannabis:
        competition *= 0.4

    breakthrough = _score(text, BREAKTHROUGH_PHRASES)
    scholarly = item.source in {"pubmed", "openalex", "arxiv", "patent"}
    if scholarly and domain in {"cannabis", "plant_tc"} and on_mission:
        breakthrough = min(1.0, breakthrough + 0.35)
    if "protocol" in text or "medium formulation" in text:
        breakthrough = min(1.0, breakthrough + 0.08)
    if cannabis and any(term in text for term in GENOMIC_TERMS + ("hlvd", "hop latent", "crispr")):
        breakthrough = min(1.0, breakthrough + 0.12)

    saturation = _score(text, SATURATION_PHRASES)
    if text.count("buy") + text.count("for sale") >= 3:
        saturation = min(1.0, saturation + 0.15)

    relevance = _relevance(text, domain, segments, entities, cannabis, on_mission)

    labels: list[str] = []
    if domain == "mammalian" and "cannabis" not in text and "hemp" not in text:
        labels.append("off-domain")
    if "off-domain" not in labels:
        if competition >= LABEL_THRESHOLD:
            labels.append("competition")
        if breakthrough >= LABEL_THRESHOLD:
            labels.append("breakthrough")
        if saturation >= LABEL_THRESHOLD:
            labels.append("saturation")
        core = {"competition", "breakthrough", "saturation"}
        if relevance >= RELEVANCE_THRESHOLD and not (set(labels) & core):
            labels.append("relevant")

    rationale_bits = [f"domain={domain}"]
    if segments:
        rationale_bits.append("segments=" + ", ".join(segments))
    if entities:
        rationale_bits.append("entities=" + ", ".join(entities[:6]))
    rationale_bits.append(
        f"scores c={competition:.2f} b={breakthrough:.2f} s={saturation:.2f} r={relevance:.2f}"
    )

    return Signal(
        item_id=item.id,
        domain=domain,
        competition=round(competition, 3),
        breakthrough=round(breakthrough, 3),
        saturation=round(saturation, 3),
        relevance=round(relevance, 3),
        labels=labels,
        segments=segments,
        entities=entities,
        rationale="; ".join(rationale_bits),
    )


def _hits(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term in text)


def _domain(text: str) -> str:
    cannabis = _hits(text, CANNABIS_TERMS)
    tc = _hits(text, TC_TERMS)
    genomic = _hits(text, GENOMIC_TERMS)
    mammalian = _hits(text, MAMMALIAN_TERMS)
    if mammalian and not cannabis and not tc:
        return "mammalian"
    if cannabis:
        return "cannabis"
    if tc:
        return "plant_tc"
    if genomic:
        return "genomic"
    if "tissue culture" in text or "micropropagation" in text:
        return "plant_tc"
    return "unknown"


def _segments(text: str, domain: str) -> list[str]:
    found: list[str] = []
    cannabis = domain == "cannabis" or _hits(text, CANNABIS_TERMS) > 0
    tc = _hits(text, TC_TERMS) > 0
    genomic = _hits(text, GENOMIC_TERMS) > 0
    tech = _hits(text, TECH_TERMS) > 0
    remediation = any(
        term in text
        for term in ("hlvd", "hop latent", "viroid", "virus-free", "remediation", "clean stock")
    )
    if cannabis and tc:
        found.append("cannabis_tc")
    if cannabis and remediation:
        found.append("remediation")
    if tc and not cannabis:
        found.append("tc_company")
    if genomic or (
        cannabis and any(term in text for term in ("genomic", "genotype", "snp", "gwas", "gblup"))
    ):
        found.append("genomic_prediction")
    if cannabis and tech:
        found.append("cannabis_tech")
    if not found and (cannabis or tc or genomic):
        found.append("adjacent")
    return found


def _relevance(
    text: str,
    domain: str,
    segments: list[str],
    entities: list[str],
    cannabis: bool,
    on_mission: bool,
) -> float:
    if domain == "mammalian":
        return 0.05
    score = 0.0
    if cannabis:
        score += 0.35
    if on_mission:
        score += 0.25
    if "cannabis_tc" in segments or "remediation" in segments:
        score += 0.25
    if "genomic_prediction" in segments:
        score += 0.2
    if "cannabis_tech" in segments:
        score += 0.15
    if "tc_company" in segments:
        score += 0.18
    if entities:
        score += 0.22
    if any(noise in text for noise in HOBBY_NOISE) and not cannabis:
        score *= 0.35
    return min(1.0, score)


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
    return min(1.0, 0.22 * hits + extra)

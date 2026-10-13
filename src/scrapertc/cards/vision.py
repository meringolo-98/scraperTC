"""Deterministic visual grade heuristics — no LLM.

Estimates centering (LR / TB border ratios), edge whitening, and rough corner wear
from listing photos using Pillow only.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from scrapertc.cards.config import vision_config
from scrapertc.cards.models import CardListing, GradeReport
from scrapertc.http import Http


def analyze_listing_image(
    listing: CardListing,
    *,
    image_bytes: bytes | None = None,
    image_url: str = "",
) -> GradeReport:
    cfg = vision_config()
    report = GradeReport(listing_id=listing.id, image_url=image_url)
    if not image_bytes:
        report.notes = "no image bytes"
        report.grade_band = "unknown"
        return report

    try:
        from PIL import Image
    except ImportError:
        report.notes = "Pillow not installed"
        report.grade_band = "unknown"
        return report

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:  # noqa: BLE001 — bad listing images are common
        report.notes = f"decode failed: {exc}"
        report.grade_band = "unknown"
        return report

    gray = image.convert("L")
    width, height = gray.size
    if width < 40 or height < 40:
        report.notes = "image too small"
        report.grade_band = "unknown"
        return report

    borders = _border_widths(gray)
    left, right, top, bottom = borders
    lr_total = left + right
    tb_total = top + bottom
    if lr_total > 0:
        report.centering_lr = round(100.0 * left / lr_total, 1)
    if tb_total > 0:
        report.centering_tb = round(100.0 * top / tb_total, 1)

    white_pct = _edge_whitening_pct(gray, cfg)
    report.whitening_edge_pct = round(white_pct, 2)
    report.corner_wear_score = round(_corner_wear(gray), 2)

    defects: list[str] = []
    warn_ratio = float(cfg.get("centering_warn_ratio") or 60)
    fail_ratio = float(cfg.get("centering_fail_ratio") or 70)
    whitening_warn = float(cfg.get("whitening_warn_pct") or 8)
    whitening_fail = float(cfg.get("whitening_fail_pct") or 18)

    for axis, value in (("LR", report.centering_lr), ("TB", report.centering_tb)):
        if value is None:
            continue
        heavy = max(value, 100 - value)
        if heavy >= fail_ratio:
            defects.append(f"heavy_off_center_{axis.lower()}")
        elif heavy >= warn_ratio:
            defects.append(f"off_center_{axis.lower()}")

    if white_pct >= whitening_fail:
        defects.append("heavy_whitening")
    elif white_pct >= whitening_warn:
        defects.append("edge_whitening")

    if report.corner_wear_score is not None and report.corner_wear_score >= 0.35:
        defects.append("corner_wear")

    report.defects = defects
    report.grade_band = _grade_band(defects, report)
    report.notes = (
        f"borders LRTB={borders}; "
        f"centering LR={report.centering_lr} TB={report.centering_tb}; "
        f"whitening={report.whitening_edge_pct}%"
    )
    return report


def analyze_listings(
    listings: list[CardListing],
    *,
    http: Http | None = None,
    limit: int = 8,
    cache_dir: Path | None = None,
) -> list[GradeReport]:
    reports: list[GradeReport] = []
    owns_http = False
    client = http
    analyzed = 0
    for listing in listings:
        if analyzed >= limit:
            break
        if listing.extra.get("catalog"):
            continue
        urls = listing.image_urls
        if not urls:
            continue
        url = urls[0]
        blob: bytes | None = None
        if cache_dir is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cached = cache_dir / f"{listing.id}.img"
            if cached.exists():
                blob = cached.read_bytes()
        if blob is None and client is not None:
            blob = client.get_bytes(url)
            if blob and cache_dir is not None:
                (cache_dir / f"{listing.id}.img").write_bytes(blob)
        if blob is None:
            continue
        reports.append(analyze_listing_image(listing, image_bytes=blob, image_url=url))
        analyzed += 1
    if owns_http and client is not None:
        client.close()
    return reports


def _border_widths(gray: Any) -> tuple[int, int, int, int]:
    """Estimate white/light margin depth from each edge until darker print."""
    width, height = gray.size
    pixels = gray.load()
    threshold = 200

    def depth_from_left() -> int:
        for x in range(width // 3):
            col = [pixels[x, y] for y in range(height // 4, 3 * height // 4)]
            if sum(1 for p in col if p < threshold) / max(1, len(col)) > 0.35:
                return x
        return width // 10

    def depth_from_right() -> int:
        for offset in range(width // 3):
            x = width - 1 - offset
            col = [pixels[x, y] for y in range(height // 4, 3 * height // 4)]
            if sum(1 for p in col if p < threshold) / max(1, len(col)) > 0.35:
                return offset
        return width // 10

    def depth_from_top() -> int:
        for y in range(height // 3):
            row = [pixels[x, y] for x in range(width // 4, 3 * width // 4)]
            if sum(1 for p in row if p < threshold) / max(1, len(row)) > 0.35:
                return y
        return height // 10

    def depth_from_bottom() -> int:
        for offset in range(height // 3):
            y = height - 1 - offset
            row = [pixels[x, y] for x in range(width // 4, 3 * width // 4)]
            if sum(1 for p in row if p < threshold) / max(1, len(row)) > 0.35:
                return offset
        return height // 10

    return depth_from_left(), depth_from_right(), depth_from_top(), depth_from_bottom()


def _edge_whitening_pct(gray: Any, cfg: dict[str, Any]) -> float:
    width, height = gray.size
    sample_pct = float(cfg.get("edge_sample_pct") or 4.0) / 100.0
    white_min = int(cfg.get("white_luma_min") or 220)
    bx = max(1, int(width * sample_pct))
    by = max(1, int(height * sample_pct))
    pixels = gray.load()
    total = 0
    white = 0
    regions = [
        (0, 0, width, by),
        (0, height - by, width, height),
        (0, 0, bx, height),
        (width - bx, 0, width, height),
    ]
    for x0, y0, x1, y1 in regions:
        for y in range(y0, y1):
            for x in range(x0, x1):
                total += 1
                if pixels[x, y] >= white_min:
                    white += 1
    return 100.0 * white / total if total else 0.0


def _corner_wear(gray: Any) -> float:
    """Higher = more dark flecks in corner patches (proxy for wear / ding)."""
    width, height = gray.size
    patch = max(4, min(width, height) // 20)
    pixels = gray.load()
    corners = [
        (0, 0),
        (width - patch, 0),
        (0, height - patch),
        (width - patch, height - patch),
    ]
    scores: list[float] = []
    for x0, y0 in corners:
        dark = 0
        n = 0
        for y in range(y0, y0 + patch):
            for x in range(x0, x0 + patch):
                n += 1
                if pixels[x, y] < 90:
                    dark += 1
        scores.append(dark / n if n else 0.0)
    return sum(scores) / len(scores) if scores else 0.0


def _grade_band(defects: list[str], report: GradeReport) -> str:
    heavy = {d for d in defects if d.startswith("heavy_") or d == "corner_wear"}
    if (
        "heavy_whitening" in heavy
        or "heavy_off_center_lr" in heavy
        or "heavy_off_center_tb" in heavy
    ):
        return "played"
    if defects:
        return "near_mint"
    if report.centering_lr is None and report.whitening_edge_pct is None:
        return "unknown"
    return "gem"

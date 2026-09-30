from __future__ import annotations

import re
from typing import Any

from scrapertc.settings import load_yaml


def cards_config() -> dict[str, Any]:
    return load_yaml("cards.yaml")


def budget_cap(default_limit: int, override: int | None = None) -> int:
    """Secondary-use cap: share of Gate 1 default_limit unless CLI overrides."""
    if override is not None:
        return max(1, override)
    cfg = cards_config()
    share = float(cfg.get("budget_share") or 0.25)
    cards_default = int(cfg.get("default_limit") or 20)
    shared = max(1, int(default_limit * share))
    return min(cards_default, shared) if cards_default else shared


def enabled_sites() -> dict[str, dict[str, Any]]:
    sites = cards_config().get("sites") or {}
    return {
        name: dict(conf)
        for name, conf in sites.items()
        if isinstance(conf, dict) and conf.get("enabled", True)
    }


def collector_enabled(name: str) -> bool:
    collectors = (cards_config().get("collectors") or {}).get(name) or {}
    return bool(collectors.get("enabled", True))


def collector_conf(name: str) -> dict[str, Any]:
    return dict((cards_config().get("collectors") or {}).get(name) or {})


def targets() -> list[dict[str, Any]]:
    return [dict(t) for t in (cards_config().get("targets") or []) if isinstance(t, dict)]


def steal_config() -> dict[str, Any]:
    return dict(cards_config().get("steal") or {})


def vision_config() -> dict[str, Any]:
    return dict(cards_config().get("vision") or {})


def build_queries(query: str | None = None) -> list[str]:
    if query:
        return [query.strip()]
    out: list[str] = []
    for target in targets():
        name = str(target.get("name") or "").strip()
        set_name = str(target.get("set") or "").strip()
        number = str(target.get("number") or "").strip()
        variants = target.get("variants") or [""]
        for variant in variants:
            parts = [p for p in (name, set_name, number, str(variant).strip()) if p]
            if parts:
                out.append(" ".join(parts))
        if name and set_name and not variants:
            out.append(f"{name} {set_name} {number}".strip())
    return out or ["pokemon card"]


_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    return _SPACE.sub(" ", text.lower().strip())

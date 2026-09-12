from __future__ import annotations

import os
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

# "priority" = the tight cannabis-first budget. "broad" = all mission keyword groups.
search_mode: ContextVar[str] = ContextVar("search_mode", default="priority")


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in [Path.cwd(), *here.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "config").is_dir():
            return candidate
    return Path.cwd()


def config_dir() -> Path:
    override = os.environ.get("SCRAPERTC_CONFIG")
    if override:
        return Path(override)
    return repo_root() / "config"


def load_yaml(name: str) -> dict[str, Any]:
    path = config_dir() / name
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    contact_email: str = "research@example.com"
    youtube_api_key: str = ""
    google_api_key: str = ""
    google_cse_id: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = ""
    github_token: str = ""
    brave_api_key: str = ""
    semantic_scholar_api_key: str = ""
    scrapertc_db: str = "data/chatter.db"

    user_agent: str = Field(default="")
    request_delay_seconds: float = 0.4
    default_limit: int = 40

    @property
    def db_path(self) -> Path:
        path = Path(self.scrapertc_db)
        if not path.is_absolute():
            path = repo_root() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    sources = load_yaml("sources.yaml")
    settings = Settings()
    if sources.get("user_agent"):
        settings.user_agent = str(sources["user_agent"])
    if not settings.user_agent:
        settings.user_agent = (
            f"scraperTC/0.1 (+https://github.com/meringolo-98/scraperTC; {settings.contact_email})"
        )
    if sources.get("request_delay_seconds") is not None:
        settings.request_delay_seconds = float(sources["request_delay_seconds"])
    if sources.get("default_limit") is not None:
        settings.default_limit = int(sources["default_limit"])
    return settings


def is_broad() -> bool:
    return search_mode.get() == "broad"


def _dedupe_terms(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for group in groups:
        for term in group:
            text = str(term).strip()
            if text and text not in seen:
                seen.add(text)
                ordered.append(text)
    return ordered


def mention_queries() -> list[str]:
    """How people talk about the space. Default net; --broad adds generic plant TC."""
    keywords = load_yaml("keywords.yaml")
    groups = ["priority", "cannabis_tc", "genomic_breeding", "cannabis_tech"]
    if is_broad():
        groups.append("tc_companies")
    buckets = [[str(t) for t in (keywords.get(group) or [])] for group in groups]
    return _dedupe_terms(*buckets) or ["cannabis tissue culture"]


def player_queries() -> list[str]:
    """Named labs / vendors / platforms from competitors.yaml — always searched."""
    names = competitors_config().get("companies") or []
    return _dedupe_terms([str(n) for n in names])


def search_queries() -> list[str]:
    """Full Gate 1 query list: mentions first, then competitor names."""
    return _dedupe_terms(mention_queries(), player_queries())


def live_queries(priority_cap: int | None = None, broad_cap: int | None = None) -> list[str]:
    """Search strings for a collector. Caps protect rate-limited APIs.

    Mentions stay first. A slice of named competitors is always mixed in so
    Gate 1 is not only technique keywords.
    """
    mentions = mention_queries()
    players = player_queries()
    cap = broad_cap if is_broad() else priority_cap
    if cap is None:
        return _dedupe_terms(mentions, players)
    player_n = min(len(players), cap // 3)
    mention_n = max(0, cap - player_n)
    return _dedupe_terms(mentions[:mention_n], players[:player_n])


def scholarly_queries() -> list[str]:
    keywords = load_yaml("keywords.yaml")
    terms = [str(t).strip() for t in (keywords.get("scholarly") or []) if str(t).strip()]
    return terms or search_queries()[:3]


def literature_queries() -> list[str]:
    """Boolean literature searches — this scrape exists to find the research."""
    return scholarly_queries() or live_queries(priority_cap=6, broad_cap=10)


def arxiv_queries() -> list[str]:
    keywords = load_yaml("keywords.yaml")
    terms = [str(t).strip() for t in (keywords.get("arxiv") or []) if str(t).strip()]
    return terms or [
        'all:"cannabis" AND (all:"tissue culture" OR all:"genomic selection")',
    ]


def all_keyword_terms() -> list[str]:
    keywords = load_yaml("keywords.yaml")
    terms: list[str] = []
    for group in (
        "priority",
        "cannabis_tc",
        "genomic_breeding",
        "cannabis_tech",
        "tc_companies",
        "mammalian",
    ):
        terms.extend(str(t) for t in (keywords.get(group) or []))
    return terms


def web_scopes() -> list[str]:
    keywords = load_yaml("keywords.yaml")
    scopes = keywords.get("web_scopes") or [""]
    return [str(s) for s in scopes]


def sources_config() -> dict[str, Any]:
    return load_yaml("sources.yaml")


def competitors_config() -> dict[str, Any]:
    return load_yaml("competitors.yaml")

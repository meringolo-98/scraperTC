from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in [Path.cwd(), *here.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return Path.cwd()


def config_path() -> Path:
    override = os.environ.get("CARDHUNT_CONFIG")
    if override:
        return Path(override)
    bundled = Path(__file__).resolve().parent / "config" / "cards.yaml"
    repo = repo_root() / "config" / "cards.yaml"
    if repo.exists():
        return repo
    return bundled


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


class HuntSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    contact_email: str = "cardhunt@localhost"
    brave_api_key: str = ""
    ebay_app_id: str = ""
    ebay_oauth_token: str = ""
    pokemontcg_api_key: str = ""
    cardhunt_db: str = "data/cardhunt.db"
    request_delay_seconds: float = 0.4
    default_limit: int = 16
    host: str = "0.0.0.0"
    port: int = 8787
    user_agent: str = Field(default="")

    @property
    def db_path(self) -> Path:
        path = Path(self.cardhunt_db)
        if not path.is_absolute():
            path = repo_root() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> HuntSettings:
    cfg = load_config()
    settings = HuntSettings()
    if not settings.user_agent:
        settings.user_agent = (
            f"CardHunt/0.1 (+https://github.com/meringolo-98/scraperTC; {settings.contact_email})"
        )
    if cfg.get("request_delay_seconds") is not None:
        settings.request_delay_seconds = float(cfg["request_delay_seconds"])
    if cfg.get("default_limit") is not None:
        settings.default_limit = int(cfg["default_limit"])
    return settings


def clear_caches() -> None:
    load_config.cache_clear()
    get_settings.cache_clear()

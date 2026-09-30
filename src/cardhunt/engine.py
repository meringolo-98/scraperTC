"""Bridge CardHunt settings into the card engine (find / vision / steals)."""

from __future__ import annotations

from cardhunt.settings import HuntSettings
from cardhunt.settings import get_settings as hunt_settings
from scrapertc.cards.demo import demo_card_listings
from scrapertc.cards.pipeline import open_card_store, run_cards
from scrapertc.settings import Settings
from scrapertc.settings import get_settings as clearable_tc_settings


def as_tc_settings(hunt: HuntSettings | None = None) -> Settings:
    hunt = hunt or hunt_settings()
    clearable_tc_settings.cache_clear()
    return Settings(
        contact_email=hunt.contact_email,
        brave_api_key=hunt.brave_api_key,
        ebay_app_id=hunt.ebay_app_id,
        ebay_oauth_token=hunt.ebay_oauth_token,
        pokemontcg_api_key=hunt.pokemontcg_api_key,
        scrapertc_cards_db=str(hunt.db_path),
        request_delay_seconds=hunt.request_delay_seconds,
        default_limit=hunt.default_limit,
        user_agent=hunt.user_agent,
    )


def hunt(
    *,
    query: str | None = None,
    sites: list[str] | None = None,
    limit: int | None = None,
    demo: bool = False,
    skip_vision: bool = False,
) -> dict:
    settings = as_tc_settings()
    store = open_card_store(settings)
    items = demo_card_listings() if demo else None
    return run_cards(
        query=query,
        sites=sites,
        limit=limit,
        settings=settings,
        store=store,
        items=items,
        skip_vision=skip_vision or demo,
    )


def listings(*, steals_only: bool = False) -> list[dict]:
    settings = as_tc_settings()
    store = open_card_store(settings)
    if steals_only:
        return store.steal_rows()
    return store.enriched_rows()


def status_payload() -> dict:
    hunt_cfg = hunt_settings()
    settings = as_tc_settings(hunt_cfg)
    store = open_card_store(settings)
    return {
        "product": "CardHunt",
        "version": "0.1.0",
        "db": str(store.path),
        "counts": store.counts(),
        "brave": bool(hunt_cfg.brave_api_key),
        "ebay": bool(hunt_cfg.ebay_oauth_token or hunt_cfg.ebay_app_id),
        "host": hunt_cfg.host,
        "port": hunt_cfg.port,
        "demo_ready": True,
    }

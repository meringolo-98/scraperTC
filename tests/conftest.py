from __future__ import annotations

from pathlib import Path

import pytest

from scrapertc.settings import Settings, get_settings
from scrapertc.store import Store


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "chatter.db"


@pytest.fixture
def store(db_path: Path) -> Store:
    return Store(db_path)


@pytest.fixture
def settings(db_path: Path) -> Settings:
    get_settings.cache_clear()
    return Settings(scrapertc_db=str(db_path), contact_email="test@example.com")

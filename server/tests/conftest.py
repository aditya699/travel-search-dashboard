"""Shared fixtures. Everything runs offline: demo sites, fake LLM, temp data dir."""

from __future__ import annotations

from datetime import date

import pytest

from app.catalog import Catalog
from app.clean.service import CleaningService
from app.core.config import CONFIG_DIR, Settings
from app.llm.fake import FakeLLM
from app.scrape.runner import scrape
from app.warehouse.build import build

END = date(2026, 11, 16)
DAYS = [date(2026, 11, 14), date(2026, 11, 15), END]


def make_settings(data_dir) -> Settings:
    return Settings(
        _env_file=None,
        llm_provider="fake",
        scrape_mode="demo",
        data_dir=data_dir,
        config_dir=CONFIG_DIR,
        clean_batch_size=25,
    )


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return Catalog.load(CONFIG_DIR)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return make_settings(tmp_path / "data")


@pytest.fixture(scope="session")
def built(tmp_path_factory, catalog) -> Settings:
    """Three days of demo scrapes, cleaned and built into a warehouse, once per run."""
    settings = make_settings(tmp_path_factory.mktemp("warehouse") / "data")
    for day in DAYS:
        scrape(settings, catalog, day)
    CleaningService(settings, catalog, FakeLLM(catalog)).run()
    build(settings, catalog)
    return settings

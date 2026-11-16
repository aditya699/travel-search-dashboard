"""Composition root: the one place that decides which LLM and which config to use."""

from __future__ import annotations

from app.catalog import Catalog
from app.core.config import Settings
from app.llm.base import LLMClient


def make_llm(settings: Settings, catalog: Catalog) -> LLMClient:
    if settings.llm_provider == "fake":
        from app.llm.fake import FakeLLM

        return FakeLLM(catalog)

    from app.llm.anthropic_client import AnthropicLLM

    key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
    return AnthropicLLM(
        model=settings.anthropic_model,
        effort=settings.anthropic_effort,
        api_key=key or None,
        max_concurrency=settings.max_concurrency,
    )


def load_catalog(settings: Settings) -> Catalog:
    return Catalog.load(settings.config_dir)

"""Settings, loaded from environment variables and ``server/.env``.

Every tunable lives here so the rest of the code never reads ``os.environ`` directly.
``server/.env.example`` documents each variable.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_DIR = Path(__file__).resolve().parents[2]
"""Absolute path of ``server/``, so relative paths work from any working directory."""

CONFIG_DIR = SERVER_DIR / "app" / "config"

Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    """Typed configuration for the pipeline, the API and the Power BI publisher."""

    model_config = SettingsConfigDict(
        env_file=SERVER_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Cleaning (LLM) --------------------------------------------------------
    llm_provider: Literal["anthropic", "fake"] = "fake"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Effort = "low"
    clean_batch_size: int = 20
    max_concurrency: int = 4

    # --- Scraping --------------------------------------------------------------
    scrape_mode: Literal["demo", "live"] = "demo"
    scrape_user_agent: str = (
        "travel-search-dashboard/0.1 (+https://github.com/aditya699/travel-search-dashboard)"
    )
    scrape_min_delay_seconds: float = 2.0

    # --- Storage ---------------------------------------------------------------
    data_dir: Path = SERVER_DIR / "data"

    # --- API -------------------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Power BI --------------------------------------------------------------
    pbi_workspace_id: str = ""
    pbi_auth: Literal["device", "service_principal"] = "device"
    pbi_tenant_id: str = "organizations"
    pbi_client_id: str = ""
    pbi_client_secret: SecretStr | None = None
    pbi_pbix_path: Path = SERVER_DIR.parent / "powerbi" / "TravelSearch.pbix"
    pbi_dataset_name: str = "Travel Search"

    # --- Data-driven config ----------------------------------------------------
    config_dir: Path = CONFIG_DIR

    @field_validator("data_dir", "pbi_pbix_path", "config_dir", mode="after")
    @classmethod
    def _resolve_relative(cls, value: Path) -> Path:
        """Read relative paths as relative to ``server/``, not the shell's cwd."""
        return value if value.is_absolute() else (SERVER_DIR / value).resolve()

    @property
    def raw_dir(self) -> Path:
        """The raw lake: one JSONL file per site per scrape date."""
        return self.data_dir / "raw"

    @property
    def clean_dir(self) -> Path:
        """Cleaned and validated listings, partitioned like the raw lake."""
        return self.data_dir / "clean"

    @property
    def cache_dir(self) -> Path:
        """Cleaned records keyed by listing id, so a re-run never pays twice."""
        return self.data_dir / "cache"

    @property
    def warehouse_path(self) -> Path:
        """The DuckDB file that holds the star schema and the views."""
        return self.data_dir / "warehouse.duckdb"

    @property
    def export_dir(self) -> Path:
        """CSV and Parquet files that Power BI Desktop reads."""
        return self.data_dir / "powerbi"

    @property
    def cors_origin_list(self) -> list[str]:
        """``CORS_ORIGINS`` split on commas."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """The process-wide settings object (cached)."""
    return Settings()

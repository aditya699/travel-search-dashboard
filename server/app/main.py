"""FastAPI app for the web preview of the dashboard.

Run from ``server/``::

    uv run uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import dashboard
from app.container import load_catalog
from app.core.config import Settings, get_settings
from app.core.logging import setup_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging()
        yield

    app = FastAPI(
        title="Travel Search Dashboard API",
        description="Fares scraped from travel sites, cleaned by Claude, filtered by RLS.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.catalog = load_catalog(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET"],
        allow_headers=["X-User-Email"],
    )

    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "warehouse": settings.warehouse_path.exists(),
            "llm_provider": settings.llm_provider,
            "scrape_mode": settings.scrape_mode,
        }

    app.include_router(dashboard.router)
    return app


app = create_app()

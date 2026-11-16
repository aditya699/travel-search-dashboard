"""Read-only endpoints behind the web preview. Every one is filtered by the viewer."""

from __future__ import annotations

from typing import Any

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api import queries
from app.api.deps import Viewer, get_catalog, get_db, get_viewer
from app.catalog import Catalog

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/users")
def list_users(catalog: Catalog = Depends(get_catalog)) -> list[dict[str, Any]]:
    """The people in user_access.json, for the demo's user switcher.

    This lists who can see what, so remove it (or put it behind an admin check)
    before you deploy for real.
    """
    return [{"email": r.email, "name": r.name, "origins": list(r.origins)} for r in catalog.access]


@router.get("/me")
def me(viewer: Viewer = Depends(get_viewer)) -> dict[str, Any]:
    return {"email": viewer.email, "name": viewer.name, "origins": viewer.origins}


@router.get("/routes")
def routes(
    viewer: Viewer = Depends(get_viewer), con: duckdb.DuckDBPyConnection = Depends(get_db)
) -> list[dict[str, Any]]:
    return queries.routes(con, viewer.origins)


@router.get("/summary")
def summary(
    viewer: Viewer = Depends(get_viewer), con: duckdb.DuckDBPyConnection = Depends(get_db)
) -> dict[str, Any]:
    return queries.summary(con, viewer.origins)


@router.get("/cheapest")
def cheapest(
    route: str | None = Query(default=None),
    viewer: Viewer = Depends(get_viewer),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[dict[str, Any]]:
    if route:
        _check_route(con, viewer, route)
    return queries.cheapest(con, viewer.origins, route)


@router.get("/trend")
def trend(
    route: str,
    viewer: Viewer = Depends(get_viewer),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[dict[str, Any]]:
    _check_route(con, viewer, route)
    return queries.trend(con, viewer.origins, route)


@router.get("/lead-time")
def lead_time(
    route: str,
    viewer: Viewer = Depends(get_viewer),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[dict[str, Any]]:
    _check_route(con, viewer, route)
    return queries.lead_time(con, viewer.origins, route)


@router.get("/sites")
def sites(
    viewer: Viewer = Depends(get_viewer), con: duckdb.DuckDBPyConnection = Depends(get_db)
) -> list[dict[str, Any]]:
    return queries.site_scorecard(con, viewer.origins)


@router.get("/quality")
def quality(
    viewer: Viewer = Depends(get_viewer), con: duckdb.DuckDBPyConnection = Depends(get_db)
) -> dict[str, Any]:
    return queries.quality(con, viewer.origins)


def _check_route(con: duckdb.DuckDBPyConnection, viewer: Viewer, route: str) -> None:
    """A route outside the viewer's airports is 'not found', not 'forbidden'.

    Saying 'forbidden' would confirm the route exists, which is itself a small leak.
    """
    allowed = {r["route_key"] for r in queries.routes(con, viewer.origins)}
    if route not in allowed:
        raise HTTPException(404, f"No route {route}.")

"""Request dependencies: a read-only warehouse connection and who is asking.

Row-level security here mirrors the Power BI role exactly: the caller's email is
looked up in ``user_access``, and every query is limited to routes that start at
their airports. The ``X-User-Email`` header stands in for real sign-in so the demo
can switch users; in production, put the API behind your SSO and read the email
from the verified token instead.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import duckdb
from fastapi import Depends, Header, HTTPException, Request

from app.catalog import Catalog
from app.core.config import Settings


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_catalog(request: Request) -> Catalog:
    return request.app.state.catalog


def get_db(settings: Settings = Depends(get_settings_dep)) -> Iterator[duckdb.DuckDBPyConnection]:
    if not settings.warehouse_path.exists():
        raise HTTPException(
            503, "No warehouse yet. Run `uv run python -m app.cli demo` in server/ first."
        )
    con = duckdb.connect(str(settings.warehouse_path), read_only=True)
    try:
        yield con
    finally:
        con.close()


@dataclass(frozen=True)
class Viewer:
    email: str
    name: str
    origins: list[str]


def get_viewer(
    x_user_email: str | None = Header(default=None),
    catalog: Catalog = Depends(get_catalog),
) -> Viewer:
    if not x_user_email:
        raise HTTPException(401, "Send X-User-Email (the dashboard does this for you).")
    origins = catalog.origins_for(x_user_email)
    if origins is None:
        raise HTTPException(403, f"{x_user_email} is not in user_access.json.")
    rule = next(r for r in catalog.access if r.email == x_user_email.strip().lower())
    return Viewer(email=rule.email, name=rule.name, origins=sorted(origins))

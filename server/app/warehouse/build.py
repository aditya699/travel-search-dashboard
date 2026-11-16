"""Build the DuckDB warehouse from the raw lake and the cleaned rows.

A full rebuild every time: it takes about a second for months of scrapes, and a
rebuild cannot drift the way incremental updates can. It is built into a temporary
file and swapped in at the end, so the API never reads a half-built warehouse.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import duckdb

from app.catalog import Catalog
from app.core.config import Settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).resolve().parent / "sql"

TABLES = [
    "fact_fare_quote",
    "quarantine",
    "dim_route",
    "dim_airport",
    "dim_carrier",
    "dim_site",
    "dim_date",
    "user_access",
]
VIEWS = [
    "v_cheapest_fares",
    "v_price_trend",
    "v_lead_time_curve",
    "v_site_spread",
    "v_data_quality",
]


def build(settings: Settings, catalog: Catalog) -> dict[str, int]:
    """Rebuild the warehouse; return row counts per table."""
    raw_glob = (settings.raw_dir / "as_of=*" / "*.jsonl").as_posix()
    clean_glob = (settings.clean_dir / "as_of=*" / "*.jsonl").as_posix()
    if not list(settings.clean_dir.glob("as_of=*/*.jsonl")):
        raise AppError("Nothing cleaned yet. Run `python -m app.cli demo` (or scrape + clean).")

    target = settings.warehouse_path
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".building.duckdb")
    tmp.unlink(missing_ok=True)

    con = duckdb.connect(str(tmp))
    try:
        stage = (SQL_DIR / "01_stage.sql").read_text(encoding="utf-8")
        con.execute(stage.format(raw_glob=raw_glob, clean_glob=clean_glob))
        _load_dimensions(con, catalog)
        con.execute((SQL_DIR / "02_model.sql").read_text(encoding="utf-8"))
        con.execute((SQL_DIR / "03_views.sql").read_text(encoding="utf-8"))
        counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}
    finally:
        con.close()
    os.replace(tmp, target)
    logger.info("Warehouse built: %s", ", ".join(f"{k}={v}" for k, v in counts.items()))
    return counts


def _load_dimensions(con: duckdb.DuckDBPyConnection, catalog: Catalog) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE dim_site (site_key VARCHAR PRIMARY KEY, site_name VARCHAR, "
        "base_url VARCHAR)"
    )
    con.executemany(
        "INSERT INTO dim_site VALUES (?, ?, ?)",
        [(s.key, s.name, s.base_url) for s in catalog.sites],
    )

    con.execute(
        "CREATE OR REPLACE TABLE dim_airport (iata VARCHAR PRIMARY KEY, city VARCHAR, "
        "state VARCHAR, lat DOUBLE, lon DOUBLE)"
    )
    con.executemany(
        "INSERT INTO dim_airport VALUES (?, ?, ?, ?, ?)",
        [(a.iata, a.city, a.state, a.lat, a.lon) for a in catalog.airports.values()],
    )

    con.execute(
        "CREATE OR REPLACE TABLE dim_carrier (carrier_code VARCHAR PRIMARY KEY, "
        "carrier_name VARCHAR)"
    )
    con.executemany(
        "INSERT INTO dim_carrier VALUES (?, ?)",
        [(c.code, c.name) for c in catalog.carriers.values()],
    )

    con.execute(
        "CREATE OR REPLACE TABLE dim_route (route_key VARCHAR PRIMARY KEY, origin VARCHAR, "
        "destination VARCHAR, origin_city VARCHAR, destination_city VARCHAR, "
        "route_label VARCHAR, distance_km INTEGER)"
    )
    rows = []
    for origin, destination in catalog.routes:
        o, d = catalog.airports[origin], catalog.airports[destination]
        rows.append(
            (
                f"{origin}-{destination}",
                origin,
                destination,
                o.city,
                d.city,
                f"{o.city} → {d.city}",
                catalog.distance_km(origin, destination),
            )
        )
    con.executemany("INSERT INTO dim_route VALUES (?, ?, ?, ?, ?, ?, ?)", rows)

    # One row per (person, airport). "*" is expanded here, so the Power BI rule stays
    # a plain lookup and an unknown email matches nothing.
    con.execute("CREATE OR REPLACE TABLE user_access (email VARCHAR, name VARCHAR, origin VARCHAR)")
    access_rows = []
    for rule in catalog.access:
        origins = sorted(catalog.airports) if "*" in rule.origins else list(rule.origins)
        access_rows.extend((rule.email, rule.name, origin) for origin in origins)
    con.executemany("INSERT INTO user_access VALUES (?, ?, ?)", access_rows)

"""Every query the web preview runs. Each one takes the viewer's allowed origins.

Filtering happens in SQL (``list_contains(?, origin)``) before any aggregation, so
a total or an average can never include a route the viewer is not allowed to see.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import duckdb


def rows(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    cursor = con.execute(sql, params)
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, _json(row), strict=True)) for row in cursor.fetchall()]


def _json(row: tuple) -> list[Any]:
    return [v.isoformat() if isinstance(v, date) else v for v in row]


def routes(con, origins: list[str]) -> list[dict[str, Any]]:
    return rows(
        con,
        "SELECT route_key, origin, destination, route_label, distance_km FROM dim_route "
        "WHERE list_contains(?, origin) ORDER BY route_key",
        [origins],
    )


def summary(con, origins: list[str]) -> dict[str, Any]:
    head = rows(
        con,
        """
        SELECT max(scrape_date) AS latest_scrape,
               min(scrape_date) AS first_scrape,
               count(DISTINCT scrape_date) AS scrape_days,
               count(*) AS quotes,
               count(DISTINCT route_key) AS routes,
               round(avg(effective_price_inr)) AS avg_fare_inr
        FROM fact_fare_quote WHERE list_contains(?, origin)
        """,
        [origins],
    )[0]
    cheapest = rows(
        con,
        """
        SELECT route_key, depart_date, cheapest_inr, carrier_code, flight_number, site_key
        FROM v_cheapest_fares WHERE list_contains(?, origin)
        ORDER BY cheapest_inr LIMIT 1
        """,
        [origins],
    )
    quality = rows(
        con,
        "SELECT sum(listings) AS listings, sum(ok) AS ok, sum(ads) AS ads, "
        "sum(rejected) AS rejected FROM v_data_quality WHERE list_contains(?, origin)",
        [origins],
    )[0]
    return {**head, "cheapest": cheapest[0] if cheapest else None, "quality": quality}


def cheapest(con, origins: list[str], route: str | None) -> list[dict[str, Any]]:
    return rows(
        con,
        """
        SELECT c.*, r.route_label, s.site_name, k.carrier_name
        FROM v_cheapest_fares c
        JOIN dim_route r USING (route_key)
        JOIN dim_site s USING (site_key)
        JOIN dim_carrier k USING (carrier_code)
        WHERE list_contains(?, c.origin) AND (? IS NULL OR c.route_key = ?)
        ORDER BY c.route_key, c.depart_date
        """,
        [origins, route, route],
    )


def trend(con, origins: list[str], route: str) -> list[dict[str, Any]]:
    """Cheapest fare per scrape date, one series per departure date."""
    return rows(
        con,
        """
        SELECT depart_date, scrape_date, days_to_departure, cheapest_inr
        FROM v_price_trend
        WHERE list_contains(?, origin) AND route_key = ?
        ORDER BY depart_date, scrape_date
        """,
        [origins, route],
    )


def lead_time(con, origins: list[str], route: str) -> list[dict[str, Any]]:
    return rows(
        con,
        """
        SELECT days_to_departure, avg_cheapest_inr, samples
        FROM v_lead_time_curve
        WHERE list_contains(?, origin) AND route_key = ?
        ORDER BY days_to_departure
        """,
        [origins, route],
    )


def site_scorecard(con, origins: list[str]) -> list[dict[str, Any]]:
    """How often each site is cheapest for the same flight, and its average premium."""
    return rows(
        con,
        """
        WITH visible AS (
            SELECT * FROM fact_fare_quote WHERE list_contains(?, origin)
        ),
        ranked AS (
            SELECT *,
                   min(effective_price_inr) OVER w AS best,
                   count(*) OVER w AS sites
            FROM visible
            WINDOW w AS (PARTITION BY scrape_date, flight_number, depart_date)
        )
        SELECT r.site_key, s.site_name,
               count(*) AS compared_quotes,
               round(100.0 * avg(CASE WHEN effective_price_inr = best THEN 1 ELSE 0 END), 1)
                   AS cheapest_pct,
               round(avg(100.0 * (effective_price_inr - best) / best), 2) AS avg_premium_pct
        FROM ranked r JOIN dim_site s USING (site_key)
        WHERE sites >= 2
        GROUP BY ALL
        ORDER BY avg_premium_pct
        """,
        [origins],
    )


def quality(con, origins: list[str]) -> dict[str, Any]:
    by_site = rows(
        con,
        """
        SELECT q.site_key, s.site_name, sum(listings) AS listings, sum(ok) AS ok,
               sum(ads) AS ads, sum(rejected) AS rejected,
               round(100.0 * sum(ok) / sum(listings), 1) AS ok_pct
        FROM v_data_quality q JOIN dim_site s USING (site_key)
        WHERE list_contains(?, q.origin)
        GROUP BY ALL ORDER BY ok_pct
        """,
        [origins],
    )
    reasons = rows(
        con,
        """
        SELECT site_key, reason, count(*) AS listings
        FROM (
            SELECT site_key, unnest(string_split(reasons, '; ')) AS reason
            FROM quarantine
            WHERE status = 'rejected' AND list_contains(?, origin)
        )
        GROUP BY ALL ORDER BY listings DESC LIMIT 8
        """,
        [origins],
    )
    samples = rows(
        con,
        """
        SELECT site_key, reasons, card_text FROM quarantine
        WHERE status = 'rejected' AND list_contains(?, origin)
        ORDER BY scrape_date DESC, listing_id LIMIT 5
        """,
        [origins],
    )
    return {"by_site": by_site, "top_reasons": reasons, "samples": samples}

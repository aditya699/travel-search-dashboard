from __future__ import annotations

import csv

import duckdb

from app.warehouse.build import TABLES, VIEWS
from app.warehouse.export import export


def _con(settings):
    return duckdb.connect(str(settings.warehouse_path), read_only=True)


def test_star_schema_is_consistent(built):
    con = _con(built)
    try:
        orphans = con.execute(
            """
            SELECT count(*) FROM fact_fare_quote f
            LEFT JOIN dim_route r USING (route_key)
            LEFT JOIN dim_site s USING (site_key)
            LEFT JOIN dim_carrier c USING (carrier_code)
            LEFT JOIN dim_date d ON d.date = f.depart_date
            WHERE r.route_key IS NULL OR s.site_key IS NULL OR c.carrier_code IS NULL
               OR d.date IS NULL
            """
        ).fetchone()[0]
        assert orphans == 0
        dupes = con.execute(
            "SELECT count(*) - count(DISTINCT quote_id) FROM fact_fare_quote"
        ).fetchone()[0]
        assert dupes == 0
        bad = con.execute(
            "SELECT count(*) FROM fact_fare_quote WHERE effective_price_inr > price_inr "
            "OR days_to_departure < 0"
        ).fetchone()[0]
        assert bad == 0
    finally:
        con.close()


def test_ads_and_rejects_go_to_quarantine(built):
    con = _con(built)
    try:
        statuses = dict(
            con.execute("SELECT status, count(*) FROM quarantine GROUP BY 1").fetchall()
        )
        assert statuses["not_fare"] > 0
        assert statuses["rejected"] > 0
        ghoomo = con.execute(
            "SELECT count(*) FROM quarantine WHERE site_key = 'ghoomo'"
        ).fetchone()[0]
        assert ghoomo > 0  # the regex cleaner cannot read Hinglish
    finally:
        con.close()


def test_views_answer_the_questions(built):
    con = _con(built)
    try:
        latest = con.execute("SELECT max(scrape_date) FROM fact_fare_quote").fetchone()[0]
        cheapest = con.execute(
            "SELECT route_key, depart_date, cheapest_inr FROM v_cheapest_fares"
        ).fetchall()
        assert cheapest
        # The view's cheapest really is the minimum in the latest scrape.
        route, depart, value = cheapest[0]
        direct = con.execute(
            "SELECT min(effective_price_inr) FROM fact_fare_quote "
            "WHERE scrape_date = ? AND route_key = ? AND depart_date = ?",
            [latest, route, depart],
        ).fetchone()[0]
        assert value == direct
        spread = con.execute("SELECT min(sites), min(spread_inr) FROM v_site_spread").fetchone()
        assert spread[0] >= 2 and spread[1] >= 0
        curve = con.execute(
            "SELECT days_to_departure, avg_cheapest_inr FROM v_lead_time_curve "
            "WHERE route_key = 'DEL-BOM' ORDER BY 1"
        ).fetchall()
        assert curve[0][1] > curve[-1][1]  # two days out costs more than a month out
    finally:
        con.close()


def test_user_access_expands_star(built, catalog):
    con = _con(built)
    try:
        head = con.execute(
            "SELECT count(*) FROM user_access WHERE email = 'head.analytics@travel.example'"
        ).fetchone()[0]
        assert head == len(catalog.airports)
    finally:
        con.close()


def test_export_writes_every_table_for_power_bi(built):
    files = export(built)
    names = {p.name for p in files}
    for table in TABLES:
        assert f"{table}.csv" in names and f"{table}.parquet" in names
    for view in VIEWS:
        assert f"{view}.csv" in names
    with (built.export_dir / "fact_fare_quote.csv").open(encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert {"quote_id", "route_key", "effective_price_inr", "scrape_date"} <= set(header)

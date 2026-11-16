-- Analysis views: the questions the dashboard answers, as SQL.
-- Every view keeps an `origin` column so row-level security can filter it.

-- The cheapest option per route and departure, from the latest scrape.
CREATE OR REPLACE VIEW v_cheapest_fares AS
WITH latest AS (SELECT max(scrape_date) AS d FROM fact_fare_quote)
SELECT
    f.route_key,
    f.origin,
    f.destination,
    f.depart_date,
    f.days_to_departure,
    min(f.effective_price_inr)                           AS cheapest_inr,
    arg_min(f.carrier_code, f.effective_price_inr)      AS carrier_code,
    arg_min(f.flight_number, f.effective_price_inr)     AS flight_number,
    arg_min(f.depart_time, f.effective_price_inr)       AS depart_time,
    arg_min(f.site_key, f.effective_price_inr)          AS site_key,
    count(*)                                             AS options
FROM fact_fare_quote AS f, latest
WHERE f.scrape_date = latest.d
GROUP BY ALL;

-- How the cheapest fare for one departure moved, scrape by scrape.
CREATE OR REPLACE VIEW v_price_trend AS
SELECT
    route_key,
    origin,
    depart_date,
    scrape_date,
    days_to_departure,
    min(effective_price_inr) AS cheapest_inr,
    round(avg(effective_price_inr)) AS average_inr
FROM fact_fare_quote
GROUP BY ALL;

-- Book early or late? Average cheapest fare by days left before departure.
CREATE OR REPLACE VIEW v_lead_time_curve AS
SELECT
    route_key,
    origin,
    days_to_departure,
    round(avg(cheapest_inr)) AS avg_cheapest_inr,
    count(*)                 AS samples
FROM v_price_trend
GROUP BY ALL;

-- The same flight on the same day, priced by more than one site.
CREATE OR REPLACE VIEW v_site_spread AS
SELECT
    scrape_date,
    route_key,
    origin,
    flight_number,
    depart_date,
    count(*)                                         AS sites,
    min(effective_price_inr)                         AS lowest_inr,
    max(effective_price_inr)                         AS highest_inr,
    max(effective_price_inr) - min(effective_price_inr) AS spread_inr,
    arg_min(site_key, effective_price_inr)           AS cheapest_site,
    arg_max(site_key, effective_price_inr)           AS dearest_site
FROM fact_fare_quote
GROUP BY ALL
HAVING count(*) >= 2;

-- Scraped versus usable, per day, site and route.
CREATE OR REPLACE VIEW v_data_quality AS
SELECT
    as_of                                            AS scrape_date,
    site                                             AS site_key,
    searched_origin || '-' || searched_destination   AS route_key,
    searched_origin                                  AS origin,
    count(*)                                         AS listings,
    count(*) FILTER (WHERE status = 'ok')            AS ok,
    count(*) FILTER (WHERE status = 'not_fare')      AS ads,
    count(*) FILTER (WHERE status = 'rejected')      AS rejected
FROM clean_listings
GROUP BY ALL;

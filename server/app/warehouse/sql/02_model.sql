-- The star schema Power BI imports: one fact table, small dimensions.
-- (dim_site, dim_airport, dim_carrier, dim_route and user_access are loaded from
-- the JSON config by warehouse/build.py before this file runs.)

-- One row per fare quote that passed validation.
CREATE OR REPLACE TABLE fact_fare_quote AS
SELECT
    c.listing_id                                         AS quote_id,
    c.as_of                                              AS scrape_date,
    c.site                                               AS site_key,
    c.searched_origin || '-' || c.searched_destination   AS route_key,
    c.searched_origin                                    AS origin,
    c.searched_destination                               AS destination,
    c.carrier_code,
    c.flight_number,
    CAST(c.depart_date AS DATE)                          AS depart_date,
    c.depart_time,
    c.arrive_time,
    c.arrives_next_day,
    c.duration_minutes,
    c.stops,
    array_to_string(c.via, ',')                          AS via,
    c.price_inr,
    c.offer_price_inr,
    coalesce(c.offer_price_inr, c.price_inr)             AS effective_price_inr,
    date_diff('day', c.as_of, CAST(c.depart_date AS DATE)) AS days_to_departure,
    c.refundable,
    c.checkin_baggage_kg,
    c.seats_left,
    c.model                                              AS cleaned_by
FROM clean_listings AS c
WHERE c.status = 'ok';

-- Everything that did not make it, and why. The data-quality page reads this.
CREATE OR REPLACE TABLE quarantine AS
SELECT
    listing_id,
    as_of                                        AS scrape_date,
    site                                         AS site_key,
    searched_origin || '-' || searched_destination AS route_key,
    searched_origin                              AS origin,
    status,
    array_to_string(reasons, '; ')               AS reasons,
    card_text,
    model                                        AS cleaned_by
FROM clean_listings
WHERE status <> 'ok';

-- A calendar covering every scrape date and every departure date.
CREATE OR REPLACE TABLE dim_date AS
WITH bounds AS (
    SELECT
        coalesce(min(least(scrape_date, depart_date)), current_date) AS first_day,
        coalesce(max(greatest(scrape_date, depart_date)), current_date) AS last_day
    FROM fact_fare_quote
)
SELECT
    CAST(d AS DATE)                AS date,
    year(d)                        AS year,
    month(d)                       AS month,
    strftime(d, '%b')              AS month_name,
    day(d)                         AS day,
    isodow(d)                      AS weekday_number,
    strftime(d, '%a')              AS weekday_name,
    isodow(d) IN (6, 7)            AS is_weekend,
    isodow(d) IN (5, 7)            AS is_peak_day
FROM bounds, range(bounds.first_day, bounds.last_day + INTERVAL 1 DAY, INTERVAL 1 DAY) AS t(d);

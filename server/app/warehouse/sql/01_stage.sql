-- Staging: the raw lake and the cleaned rows, read straight from JSONL.
-- Columns are declared, not inferred, so a day where every value is null
-- cannot change a column's type.

CREATE OR REPLACE TABLE raw_listings AS
SELECT *
FROM read_json(
    '{raw_glob}',
    format = 'newline_delimited',
    hive_partitioning = false,
    columns = {{
        listing_id: 'VARCHAR',
        content_hash: 'VARCHAR',
        site: 'VARCHAR',
        source_ref: 'VARCHAR',
        url: 'VARCHAR',
        origin: 'VARCHAR',
        destination: 'VARCHAR',
        depart_date: 'DATE',
        as_of: 'DATE',
        scraped_at: 'TIMESTAMPTZ',
        page_context: 'VARCHAR',
        card_text: 'VARCHAR'
    }}
);

CREATE OR REPLACE TABLE clean_listings AS
SELECT *
FROM read_json(
    '{clean_glob}',
    format = 'newline_delimited',
    hive_partitioning = false,
    columns = {{
        listing_id: 'VARCHAR',
        content_hash: 'VARCHAR',
        site: 'VARCHAR',
        source_ref: 'VARCHAR',
        as_of: 'DATE',
        searched_origin: 'VARCHAR',
        searched_destination: 'VARCHAR',
        searched_depart_date: 'DATE',
        card_text: 'VARCHAR',
        status: 'VARCHAR',
        reasons: 'VARCHAR[]',
        carrier_code: 'VARCHAR',
        model: 'VARCHAR',
        is_fare: 'BOOLEAN',
        carrier: 'VARCHAR',
        flight_number: 'VARCHAR',
        origin: 'VARCHAR',
        destination: 'VARCHAR',
        depart_date: 'VARCHAR',
        depart_time: 'VARCHAR',
        arrive_time: 'VARCHAR',
        arrives_next_day: 'BOOLEAN',
        duration_minutes: 'INTEGER',
        stops: 'INTEGER',
        via: 'VARCHAR[]',
        price_inr: 'INTEGER',
        offer_price_inr: 'INTEGER',
        refundable: 'BOOLEAN',
        checkin_baggage_kg: 'INTEGER',
        seats_left: 'INTEGER'
    }}
);

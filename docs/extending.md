# Extending the project

## Add a site

1. Read the site's terms of service and robots.txt. If automated access is not
   allowed, stop here and look for an official API or affiliate feed instead.
2. Open a search results page in your browser, right-click a result → **Inspect**, and
   find three things:
   - a CSS selector that matches one result card (`card_selector`),
   - an attribute on that card that identifies it (`id_attr`; if there is none, the
     parser falls back to the card's position),
   - a selector for the page header that says which search this is (`context_selector`).
3. Add an entry to `server/app/config/sites.json` with the search URL pattern
   (`{origin}`, `{destination}`, `{depart_date}` are filled in for you).
4. `SCRAPE_MODE=live`, then `uv run python -m app.cli scrape --site <key>` and look at
   `data/raw/as_of=<today>/<key>.jsonl`. If the card text looks right, `clean` it and
   check the quarantine table for what the checks rejected.

Some sites render results with JavaScript, so the HTML the fetcher gets has no cards.
The usual answer is the JSON API the page itself calls (look in the browser's Network
tab), within the site's terms. A headless browser is the heavier option.

## Add a carrier or an airport

Edit `carriers.json` (with every spelling you see in `quarantine.reasons` as "unknown
carrier") or `airports.json`. No code changes. Rebuild with `build`.

## Add hotels

1. Add `HotelRecord` and `HotelBatch` next to `CleanRecord` in `app/clean/schema.py`
   (hotel name, city, check-in date, nights, price per night, rating, free
   cancellation).
2. A second prompt in `app/llm/prompts/` and a `kind` field per site in `sites.json`
   (`flight` or `hotel`) so the cleaning service picks the right schema.
3. `fact_hotel_quote` in `02_model.sql`, sharing `dim_date` and a new `dim_city`.
4. RLS: relate `dim_city` to `dim_airport`, or filter it with its own rule in the same
   `Desk` role.

## Use Postgres instead of DuckDB

DuckDB is a file, which is perfect on a laptop. For a shared warehouse that Power BI
can refresh on a schedule without a gateway, use a hosted Postgres:

- keep the SQL (it is close to standard; `arg_min` becomes `DISTINCT ON` or a window),
- load the JSONL with `COPY` or pandas, and
- in Power BI, replace the Parquet queries with **Get data → PostgreSQL**.

## Run it every day

A GitHub Actions workflow on a schedule:

```yaml
on:
  schedule:
    - cron: "30 1 * * *"   # 07:00 IST
jobs:
  pipeline:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: server } }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync
      - run: uv run python -m app.cli scrape
      - run: uv run python -m app.cli clean
        env:
          LLM_PROVIDER: anthropic
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - run: uv run python -m app.cli build
      - run: uv run python -m app.cli export
```

The raw lake and cache must persist between runs for history and for the cache to
save money: store `server/data/` in cloud storage (S3, Azure Blob, R2) and sync it at
the start and end of the job.

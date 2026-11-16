"""The scraping layer: run the search plan on every enabled site, write the raw lake.

Output is append-only and partitioned by scrape date, one JSONL file per site::

    data/raw/as_of=2026-11-16/skybazaar.jsonl

Each line is one card exactly as scraped (text, page header, which search it came
from). Nothing is cleaned here, so a better cleaner later can re-run over old scrapes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import httpx

from app.catalog import Catalog
from app.core.config import Settings
from app.core.errors import ScrapeError
from app.scrape.demo_sites import DemoSites, depart_dates
from app.scrape.fetcher import Fetcher
from app.scrape.parser import parse_page

logger = logging.getLogger(__name__)


@dataclass
class ScrapeReport:
    as_of: date
    pages: int = 0
    cards: int = 0
    errors: list[str] = field(default_factory=list)


def make_client(settings: Settings, catalog: Catalog, as_of: date) -> httpx.Client:
    """A real HTTP client in live mode; the built-in demo sites in demo mode."""
    if settings.scrape_mode == "demo":
        return httpx.Client(transport=DemoSites(catalog, as_of).transport())
    return httpx.Client(timeout=20.0, follow_redirects=True)


def scrape(
    settings: Settings,
    catalog: Catalog,
    as_of: date,
    *,
    client: httpx.Client | None = None,
    sites: list[str] | None = None,
) -> ScrapeReport:
    """Scrape every (site, route, departure) in the plan as of ``as_of``."""
    demo = settings.scrape_mode == "demo"
    own_client = client is None
    client = client or make_client(settings, catalog, as_of)
    fetcher = Fetcher(
        client,
        user_agent=settings.scrape_user_agent,
        min_delay_seconds=settings.scrape_min_delay_seconds,
        # The demo sites are in-process, so waiting between requests would only slow
        # you down. The delay logic still runs; it just does not sleep.
        sleep=(lambda _seconds: None) if demo else time.sleep,
    )
    report = ScrapeReport(as_of=as_of)
    partition = settings.raw_dir / f"as_of={as_of.isoformat()}"
    partition.mkdir(parents=True, exist_ok=True)
    scraped_at = datetime.now(UTC).isoformat(timespec="seconds")

    try:
        for site in catalog.enabled_sites:
            if sites and site.key not in sites:
                continue
            lines: list[str] = []
            for origin, destination in catalog.routes:
                for depart in depart_dates(as_of, catalog.depart_offsets_days):
                    url = site.search_url(origin, destination, depart.isoformat())
                    try:
                        page = fetcher.get(url, site_delay_seconds=site.min_delay_seconds)
                    except ScrapeError as exc:
                        report.errors.append(str(exc))
                        logger.warning("%s", exc)
                        continue
                    report.pages += 1
                    context, cards = parse_page(page, site)
                    for card in cards:
                        lines.append(
                            json.dumps(
                                {
                                    "listing_id": _hash(site.key, as_of, url, card.source_ref)[:16],
                                    "content_hash": _hash(
                                        site.key, origin, destination, depart, context, card.text
                                    )[:20],
                                    "site": site.key,
                                    "source_ref": card.source_ref,
                                    "url": url,
                                    "origin": origin,
                                    "destination": destination,
                                    "depart_date": depart.isoformat(),
                                    "as_of": as_of.isoformat(),
                                    "scraped_at": scraped_at,
                                    "page_context": context,
                                    "card_text": card.text,
                                },
                                ensure_ascii=False,
                            )
                        )
                    report.cards += len(cards)
            # One file per site per day; re-running the same day replaces it.
            (partition / f"{site.key}.jsonl").write_text(
                "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
            )
            logger.info("%s %s: %d cards", as_of, site.key, len(lines))
    finally:
        if own_client:
            client.close()
    return report


def _hash(*parts: object) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode("utf-8")).hexdigest()

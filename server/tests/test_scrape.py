from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from app.core.errors import ScrapeError
from app.scrape.demo_sites import DemoSites
from app.scrape.fetcher import Fetcher
from app.scrape.parser import parse_page
from app.scrape.runner import scrape

AS_OF = date(2026, 11, 16)
DEPART = date(2026, 11, 25)


def test_demo_pages_are_deterministic(catalog):
    a = DemoSites(catalog, AS_OF).render("skybazaar", "DEL", "BOM", DEPART)
    b = DemoSites(catalog, AS_OF).render("skybazaar", "DEL", "BOM", DEPART)
    assert a == b
    later = DemoSites(catalog, date(2026, 11, 20)).render("skybazaar", "DEL", "BOM", DEPART)
    assert later != a  # fares move between scrape days


def test_same_flight_appears_on_several_sites(catalog):
    sites = DemoSites(catalog, AS_OF)
    numbers = {
        key: {i.flight.number for i in sites.listings(key, "DEL", "BOM", DEPART) if i.flight}
        for key in ("skybazaar", "paisaflights", "kitetravel", "ghoomo")
    }
    shared = set.intersection(*numbers.values())
    assert len(shared) >= 3


def test_fares_climb_close_to_departure(catalog):
    sites = DemoSites(catalog, AS_OF)
    flight = sites.schedule("DEL", "BOM")[0]
    far = sites.fare("skybazaar", flight, date(2026, 12, 16))
    near = sites.fare("skybazaar", flight, date(2026, 11, 18))
    assert near > far * 1.3


@pytest.mark.parametrize("site_key", ["skybazaar", "paisaflights", "kitetravel", "ghoomo"])
def test_parser_finds_every_card(catalog, site_key):
    sites = DemoSites(catalog, AS_OF)
    page = sites.render(site_key, "DEL", "BOM", DEPART)
    context, cards = parse_page(page, catalog.site(site_key))
    truth = sites.truth(site_key, "DEL", "BOM", DEPART)
    assert context
    assert [c.source_ref for c in cards] == list(truth)
    assert all("Login" not in c.text for c in cards)  # navigation is not a card


def test_kite_ad_card_is_in_the_page(catalog):
    page = DemoSites(catalog, AS_OF).render("kitetravel", "DEL", "BOM", DEPART)
    _, cards = parse_page(page, catalog.site("kitetravel"))
    assert any("/night" in c.text for c in cards)


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_fetcher_respects_robots_and_crawl_delay(catalog):
    clock = FakeClock()
    client = httpx.Client(transport=DemoSites(catalog, AS_OF).transport())
    fetcher = Fetcher(
        client, user_agent="test", min_delay_seconds=1.0, clock=clock, sleep=clock.sleep
    )
    site = catalog.site("paisaflights")  # robots.txt says Crawl-delay: 3
    url = site.search_url("DEL", "BOM", DEPART.isoformat())
    fetcher.get(url)
    fetcher.get(url)
    assert clock.slept == [3.0]
    with pytest.raises(ScrapeError, match=r"robots\.txt"):
        fetcher.get("https://paisaflights.example/account/bookings")


def test_fetcher_retries_429_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, text="<html>ok</html>")

    clock = FakeClock()
    fetcher = Fetcher(
        httpx.Client(transport=httpx.MockTransport(handler)),
        user_agent="test",
        min_delay_seconds=0,
        clock=clock,
        sleep=clock.sleep,
    )
    assert "ok" in fetcher.get("https://x.example/page")
    assert 7.0 in clock.slept


def test_fetcher_gives_up_on_404():
    transport = httpx.MockTransport(lambda r: httpx.Response(404))
    fetcher = Fetcher(httpx.Client(transport=transport), user_agent="t", min_delay_seconds=0)
    with pytest.raises(ScrapeError, match="404"):
        fetcher.get("https://x.example/missing")


def test_scrape_writes_partitioned_raw_lake(settings, catalog):
    report = scrape(settings, catalog, AS_OF, sites=["skybazaar"])
    assert report.pages == len(catalog.routes) * len(catalog.depart_offsets_days)
    path = settings.raw_dir / "as_of=2026-11-16" / "skybazaar.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == report.cards
    assert {"listing_id", "content_hash", "card_text", "page_context"} <= set(rows[0])
    assert len({r["listing_id"] for r in rows}) == len(rows)
    # Re-running the same day replaces the file instead of duplicating rows.
    scrape(settings, catalog, AS_OF, sites=["skybazaar"])
    assert len(path.read_text(encoding="utf-8").splitlines()) == len(rows)

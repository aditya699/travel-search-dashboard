from __future__ import annotations

import json
from datetime import date

from app.clean.evaluate import evaluate
from app.clean.rules import clean_listing
from app.clean.schema import CleanBatch, CleanRecord
from app.clean.service import CleaningService
from app.clean.validate import validate
from app.llm.fake import FakeLLM
from app.scrape.runner import scrape

AS_OF = date(2026, 11, 16)


def _item(text: str, **searched) -> dict:
    return {
        "id": "x1",
        "site": "test",
        "searched": {
            "origin": "DEL",
            "destination": "BOM",
            "depart_date": "2026-11-25",
            **searched,
        },
        "page_header": "",
        "text": text,
    }


def test_rules_read_paisaflights_cashback(catalog):
    text = (
        "KESTREL AIR | KS 241 | 6:15 AM | 8:30 AM | 135 mins | 0 stops | Rs. 4599/- | "
        "Cashback ₹200 with code PAISA200 (you pay ₹4,399) | 🔥 Free meal | Check-in 15kg | 3 left"
    )
    r = clean_listing(_item(text), catalog)
    assert (r.flight_number, r.depart_time, r.arrive_time) == ("KS241", "06:15", "08:30")
    assert (r.duration_minutes, r.stops, r.price_inr, r.offer_price_inr) == (135, 0, 4599, 4399)
    assert (r.checkin_baggage_kg, r.seats_left) == (15, 3)


def test_rules_read_kite_thin_space_and_next_day(catalog):
    text = (
        "Kestrel · KS241 · Departs 2240 hrs, arrives 0105 hrs (+1) · 2:25 hrs · Direct · "
        "₹ 6 499 · Cabin 7kg + Check-in 20kg · Non-refundable · coupon KITE150 → ₹ 6 349"
    )
    r = clean_listing(_item(text), catalog)
    assert (r.depart_time, r.arrive_time, r.arrives_next_day) == ("22:40", "01:05", True)
    assert (r.duration_minutes, r.price_inr, r.offer_price_inr) == (145, 6499, 6349)
    assert r.refundable is False


def test_rules_mark_hotel_ad_as_not_a_fare(catalog):
    r = clean_listing(
        _item("Sponsored · Stay at Hotel Marigold, Mumbai from ₹ 2 199/night"), catalog
    )
    assert r.is_fare is False and r.price_inr is None


def _good(**changes) -> CleanRecord:
    base = dict(
        listing_id="x1",
        is_fare=True,
        carrier="Kestrel Air",
        flight_number="KS241",
        origin="DEL",
        destination="BOM",
        depart_date="2026-11-25",
        depart_time="06:15",
        arrive_time="08:30",
        arrives_next_day=False,
        duration_minutes=135,
        stops=0,
        via=[],
        price_inr=4599,
        offer_price_inr=None,
        refundable=None,
        checkin_baggage_kg=15,
        seats_left=None,
    )
    base.update(changes)
    return CleanRecord(**base)


RAW = {"origin": "DEL", "destination": "BOM", "depart_date": "2026-11-25"}


def test_validate_accepts_a_good_row(catalog):
    verdict = validate(_good(), RAW, catalog)
    assert verdict.status == "ok" and verdict.carrier_code == "KS"


def test_validate_catches_what_an_llm_can_get_wrong(catalog):
    cases = {
        "missing price_inr": _good(price_inr=None),
        "outside": _good(price_inr=45),
        "offer price above": _good(offer_price_inr=5000),
        "do not fit": _good(duration_minutes=300),
        "is not the search": _good(destination="BLR"),
        "unknown carrier": _good(carrier="Air Imaginary", flight_number="ZZ123"),
        "does not match": _good(carrier="Monsoon Airways"),
        "is not HH:MM": _good(depart_time="6.15am"),
    }
    for reason, record in cases.items():
        verdict = validate(record, RAW, catalog)
        assert verdict.status == "rejected", reason
        assert any(reason in r for r in verdict.reasons), (reason, verdict.reasons)


def test_validate_handles_overnight_flights(catalog):
    r = _good(depart_time="22:40", arrive_time="01:05", arrives_next_day=True, duration_minutes=145)
    assert validate(r, RAW, catalog).status == "ok"


async def test_fake_llm_speaks_the_cleaning_protocol(catalog):
    content = json.dumps({"listings": [_item("Saffron Wings SW-512 06:00 → 08:10 2h 10m ₹5,199")]})
    batch = await FakeLLM(catalog).structured(system="", content=content, schema=CleanBatch)
    assert batch.records[0].flight_number == "SW512"


def test_cleaning_uses_the_cache_on_rerun(settings, catalog):
    scrape(settings, catalog, AS_OF, sites=["skybazaar"])
    llm = FakeLLM(catalog)
    first = CleaningService(settings, catalog, llm).run()
    calls = llm.calls
    second = CleaningService(settings, catalog, llm).run()
    assert first.cache_hits == 0 and first.listings > 0
    assert second.cache_hits == second.listings
    assert llm.calls == calls  # no new LLM calls


class FlakyLLM(FakeLLM):
    """Drops the last record of every batch, the way a model sometimes does."""

    async def structured(self, *, system, content, schema):
        batch = await super().structured(system=system, content=content, schema=schema)
        return schema(records=batch.records[:-1])


def test_missing_records_are_quarantined_not_lost(settings, catalog):
    scrape(settings, catalog, AS_OF, sites=["kitetravel"])
    report = CleaningService(settings, catalog, FlakyLLM(catalog)).run()
    assert any("skipped" in e for e in report.errors)
    assert report.status["rejected"] >= 1
    assert sum(report.status.values()) == report.listings


def test_eval_scores_rules_against_truth(built, catalog):
    report = evaluate(built, catalog)
    accuracy = report.field_accuracy()
    assert report.listings > 1000
    # The rules know three of the four sites, so they ace those and miss Ghoomo.
    assert accuracy["price_inr"] > 0.99
    assert accuracy["depart_time"] < 0.9
    assert 0.6 < report.row_accuracy < 0.9

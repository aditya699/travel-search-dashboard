"""A regex cleaner: the offline baseline the LLM is measured against.

It knows the formats of the three demo sites and nothing else, which is the point:
every new site breaks rules like these, and an LLM copes. ``LLM_PROVIDER=fake`` uses
this so the pipeline, tests and dashboard all run with no key and no cost, and
``eval`` tells you how much better (or not) Claude does on the same listings.
"""

from __future__ import annotations

import re
from typing import Any

from app.catalog import Catalog
from app.clean.schema import CleanRecord

_SEP = "[,  ]"
NUMBER = rf"(\d{{1,3}}(?:{_SEP}\d{{2,3}})+|\d{{1,3}}(?: \d{{3}})+|\d+)"
AMOUNT = re.compile(rf"(?:₹|Rs\.?|INR)\s*{NUMBER}")
OFFER = re.compile(rf"(?:you pay|→)\s*(?:₹|Rs\.?|INR)\s*{NUMBER}", re.I)
TIME_12 = re.compile(r"\b(1[0-2]|0?[1-9]):([0-5]\d)\s*(AM|PM)\b", re.I)
TIME_HRS = re.compile(r"\b([01]\d|2[0-3])([0-5]\d)\s*hrs\b")
TIME_24 = re.compile(r"\b([01]\d|2[0-3]):([0-5]\d)\b(?!\s*(?:AM|PM|hrs))", re.I)
DURATION = [
    (re.compile(r"\b(\d{1,2})h\s*(\d{1,2})m\b"), lambda m: int(m[1]) * 60 + int(m[2])),
    (re.compile(r"\b(\d{2,4})\s*mins?\b"), lambda m: int(m[1])),
    (re.compile(r"\b(\d{1,2}):([0-5]\d)\s*hrs\b"), lambda m: int(m[1]) * 60 + int(m[2])),
]
NONSTOP = re.compile(r"\bnon-?stop\b|\bdirect\b|\b0 stops\b", re.I)
STOPS = re.compile(r"\b(\d)\s*stops?\b", re.I)
VIA = re.compile(r"(?:via|stops? \()\s*([A-Z]{3}(?:,\s*[A-Z]{3})*)")
FLIGHT = re.compile(r"\b([A-Z0-9]{2})[\s-]?(\d{3,4})\b")
BAGGAGE = re.compile(r"check-in\s*(\d{1,2})\s*kg|\b(\d{1,2})\s*kg check-in", re.I)
SEATS = re.compile(r"\b(\d{1,2})\s*(?:seats?\s*)?left\b", re.I)
NEXT_DAY = re.compile(r"\+1\b")


def clean_listing(item: dict[str, Any], catalog: Catalog) -> CleanRecord:
    """Clean one listing as the LLM would, using only regexes."""
    text: str = item["text"]
    searched = item.get("searched") or {}
    flight = _flight_number(text, catalog)
    if flight is None or "/night" in text:
        return _empty(item["id"])

    times = _times(text)
    stops: int | None = None
    if NONSTOP.search(text):
        stops = 0
    elif m := STOPS.search(text):
        stops = int(m[1])
    via_match = VIA.search(text)
    via = [code.strip() for code in via_match[1].split(",")] if via_match else []

    offer_match = OFFER.search(text)
    price = None
    for m in AMOUNT.finditer(text):
        before = text[max(0, m.start() - 12) : m.start()].lower()
        if "cashback" in before or (offer_match and m.start() >= offer_match.start()):
            continue
        price = _number(m[1])
        break

    refundable: bool | None = None
    if re.search(r"non-?refundable", text, re.I):
        refundable = False
    elif re.search(r"refundable", text, re.I):
        refundable = True

    baggage = BAGGAGE.search(text)
    seats = SEATS.search(text)
    carrier_code = flight[:2]
    return CleanRecord(
        listing_id=item["id"],
        is_fare=True,
        carrier=catalog.carriers[carrier_code].name,
        flight_number=flight,
        origin=searched.get("origin"),
        destination=searched.get("destination"),
        depart_date=searched.get("depart_date"),
        depart_time=times[0] if len(times) > 0 else None,
        arrive_time=times[1] if len(times) > 1 else None,
        arrives_next_day=bool(NEXT_DAY.search(text)),
        duration_minutes=_duration(text),
        stops=stops,
        via=via,
        price_inr=price,
        offer_price_inr=_number(offer_match[1]) if offer_match else None,
        refundable=refundable,
        checkin_baggage_kg=int(baggage[1] or baggage[2]) if baggage else None,
        seats_left=int(seats[1]) if seats else None,
    )


def _flight_number(text: str, catalog: Catalog) -> str | None:
    for m in FLIGHT.finditer(text):
        if m[1] in catalog.carriers:
            return f"{m[1]}{m[2]}"
    return None


def _times(text: str) -> list[str]:
    found: list[tuple[int, str]] = []
    for m in TIME_12.finditer(text):
        hour = int(m[1]) % 12 + (12 if m[3].upper() == "PM" else 0)
        found.append((m.start(), f"{hour:02d}:{m[2]}"))
    for m in TIME_HRS.finditer(text):
        found.append((m.start(), f"{m[1]}:{m[2]}"))
    for m in TIME_24.finditer(text):
        found.append((m.start(), f"{m[1]}:{m[2]}"))
    return [t for _, t in sorted(found)]


def _duration(text: str) -> int | None:
    for pattern, minutes in DURATION:
        if m := pattern.search(text):
            return minutes(m)
    return None


def _number(raw: str) -> int:
    return int(re.sub(r"\D", "", raw))


def _empty(listing_id: str) -> CleanRecord:
    return CleanRecord(
        listing_id=listing_id,
        is_fare=False,
        carrier=None,
        flight_number=None,
        origin=None,
        destination=None,
        depart_date=None,
        depart_time=None,
        arrive_time=None,
        arrives_next_day=False,
        duration_minutes=None,
        stops=None,
        via=[],
        price_inr=None,
        offer_price_inr=None,
        refundable=None,
        checkin_baggage_kg=None,
        seats_left=None,
    )

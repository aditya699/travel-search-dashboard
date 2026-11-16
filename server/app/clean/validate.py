"""Deterministic checks on every cleaned listing, LLM or not.

The model is good, but a dashboard is only as trustworthy as its worst row. These
checks are plain Python and cheap, and anything that fails goes to the quarantine
table with a reason, instead of quietly into the fact table. The data-quality page
of the dashboard is built from the result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.catalog import Catalog
from app.clean.schema import CleanRecord

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
REQUIRED = ["carrier", "flight_number", "depart_time", "arrive_time", "price_inr"]
MIN_PRICE, MAX_PRICE = 500, 150_000
DURATION_TOLERANCE_MIN = 10


@dataclass
class Verdict:
    status: str  # "ok" | "not_fare" | "rejected"
    reasons: list[str] = field(default_factory=list)
    carrier_code: str | None = None


def validate(record: CleanRecord, raw: dict[str, Any], catalog: Catalog) -> Verdict:
    """Check one cleaned record against the raw listing it came from."""
    if not record.is_fare:
        return Verdict("not_fare", ["not a flight (ad or banner)"])

    reasons: list[str] = []
    for name in REQUIRED:
        if getattr(record, name) in (None, ""):
            reasons.append(f"missing {name}")

    carrier_code = catalog.carrier_code(record.carrier)
    if record.flight_number and len(record.flight_number) >= 2:
        prefix = record.flight_number[:2].upper()
        if prefix in catalog.carriers:
            if carrier_code and carrier_code != prefix:
                reasons.append(f"carrier {record.carrier!r} does not match {record.flight_number}")
            carrier_code = carrier_code or prefix
    if record.carrier and carrier_code is None:
        reasons.append(f"unknown carrier {record.carrier!r} (add it to carriers.json)")

    if record.origin != raw["origin"] or record.destination != raw["destination"]:
        reasons.append(
            f"route {record.origin}-{record.destination} is not the search "
            f"{raw['origin']}-{raw['destination']}"
        )
    if record.depart_date != raw["depart_date"]:
        reasons.append(f"date {record.depart_date} is not the searched {raw['depart_date']}")

    if record.price_inr is not None and not MIN_PRICE <= record.price_inr <= MAX_PRICE:
        reasons.append(f"price ₹{record.price_inr} outside ₹{MIN_PRICE}-₹{MAX_PRICE}")
    if (
        record.offer_price_inr is not None
        and record.price_inr is not None
        and record.offer_price_inr > record.price_inr
    ):
        reasons.append("offer price above listed price")

    for name in ("depart_time", "arrive_time"):
        value = getattr(record, name)
        if value and not HHMM.match(value):
            reasons.append(f"{name} {value!r} is not HH:MM")

    if record.stops is not None and not 0 <= record.stops <= 3:
        reasons.append(f"{record.stops} stops")
    if record.stops is not None and record.stops != len(record.via) and record.via:
        reasons.append(f"{record.stops} stops but via {record.via}")

    if (
        record.duration_minutes is not None
        and record.depart_time
        and record.arrive_time
        and HHMM.match(record.depart_time)
        and HHMM.match(record.arrive_time)
    ):
        elapsed = _minutes(record.arrive_time) - _minutes(record.depart_time)
        if record.arrives_next_day or elapsed < 0:
            elapsed += 1440
        if abs(elapsed - record.duration_minutes) > DURATION_TOLERANCE_MIN:
            reasons.append(
                f"times {record.depart_time}-{record.arrive_time} do not fit a "
                f"{record.duration_minutes} min duration"
            )

    return Verdict("rejected" if reasons else "ok", reasons, carrier_code)


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)

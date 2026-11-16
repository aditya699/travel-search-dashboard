"""The shape a scraped listing is cleaned into.

Claude fills :class:`CleanBatch` through structured outputs, so what comes back is
validated JSON in exactly this shape. The demo sites produce the same shape as ground
truth, which is how ``python -m app.cli eval`` scores the cleaner field by field.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CleanRecord(BaseModel):
    """One search result, cleaned. Unknown values are null, never guessed."""

    listing_id: str = Field(description="The id of the listing, copied exactly from the input.")
    is_fare: bool = Field(
        description="True for a bookable flight. False for ads, hotel offers, banners."
    )
    carrier: str | None = Field(description="Airline name as written, e.g. 'Kestrel Air'.")
    flight_number: str | None = Field(
        description="Two-letter code and digits, no space or dash, e.g. 'KS241'."
    )
    origin: str | None = Field(description="IATA code of the departure airport, e.g. 'DEL'.")
    destination: str | None = Field(description="IATA code of the arrival airport.")
    depart_date: str | None = Field(description="Departure date as YYYY-MM-DD.")
    depart_time: str | None = Field(description="Departure time, 24-hour HH:MM.")
    arrive_time: str | None = Field(description="Arrival time, 24-hour HH:MM.")
    arrives_next_day: bool = Field(description="True when the arrival is on the next day.")
    duration_minutes: int | None = Field(description="Total journey time in minutes.")
    stops: int | None = Field(description="Number of stops; 0 for non-stop or direct.")
    via: list[str] = Field(description="IATA codes of stopover airports, in order.")
    price_inr: int | None = Field(
        description="The listed fare in rupees, before any cashback or coupon."
    )
    offer_price_inr: int | None = Field(
        description="What you pay after a cashback or coupon the listing states, else null."
    )
    refundable: bool | None = Field(description="True, False, or null when not stated.")
    checkin_baggage_kg: int | None = Field(description="Check-in baggage allowance in kg.")
    seats_left: int | None = Field(description="Seats left when the listing says so.")


class CleanBatch(BaseModel):
    """A batch of cleaned listings: one record per input listing, same order."""

    records: list[CleanRecord]


FIELDS_SCORED = [
    "is_fare",
    "carrier",
    "flight_number",
    "origin",
    "destination",
    "depart_date",
    "depart_time",
    "arrive_time",
    "arrives_next_day",
    "duration_minutes",
    "stops",
    "via",
    "price_inr",
    "offer_price_inr",
    "refundable",
    "checkin_baggage_kg",
    "seats_left",
]
"""Fields ``eval`` compares against the demo sites' ground truth."""

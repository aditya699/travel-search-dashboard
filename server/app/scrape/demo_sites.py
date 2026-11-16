"""Three fictional travel sites, generated in code, so the whole pipeline runs offline.

Each site lists the same flights with its own markup and its own mess: SkyBazaar
writes "₹4,599" and "2h 15m", PaisaFlights writes "Rs. 4599/-", "135 mins" and 12-hour
times with cashback offers, Kite Travel packs everything into one line with "0615 hrs",
thin-space prices, coupons and a sponsored hotel card. That mess is the reason the
cleaning layer exists.

Fares are deterministic: a seeded model of distance, days to departure, weekday,
carrier and site, plus noise. The same (site, search, scrape date) always gives the
same page, and :meth:`DemoSites.truth` returns the clean answer for every card, which
is what ``eval`` scores the cleaner against.

:meth:`DemoSites.transport` plugs the sites into ``httpx`` as a mock transport, so the
scraper runs its real code path (robots.txt, rate limit, HTTP, HTML parsing) against them.
"""

from __future__ import annotations

import hashlib
import html
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx

from app.catalog import Catalog
from app.clean.schema import CleanRecord

SITE_FACTOR = {"skybazaar": 1.0, "paisaflights": 0.985, "kitetravel": 1.02, "ghoomo": 0.995}
CARRIER_FACTOR = {"KS": 1.0, "MW": 0.92, "SW": 1.08, "IJ": 0.97}
HUBS = ["DEL", "BOM", "BLR", "HYD"]
NNBSP = " "  # narrow no-break space, the way some sites group digits

HOTELS = ["Hotel Marigold", "The Banyan Residency", "Lotus Courtyard", "Hotel Neelkamal"]


def _rng(*parts: object) -> random.Random:
    seed = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16]
    return random.Random(int(seed, 16))


def _ref(*parts: object) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:10].upper()


@dataclass(frozen=True)
class Flight:
    carrier_code: str
    carrier_name: str
    number: str  # "KS241"
    origin: str
    destination: str
    dep_minutes: int  # minutes after midnight
    duration: int
    stops: int
    via: tuple[str, ...]

    @property
    def arr_minutes(self) -> int:
        return self.dep_minutes + self.duration


@dataclass(frozen=True)
class Listing:
    """One card on one page, with the clean answer behind it."""

    site: str
    source_ref: str
    flight: Flight | None  # None for an ad
    truth: CleanRecord
    ad_text: str = ""


class DemoSites:
    """Renders search pages for the fictional sites as they looked on ``as_of``."""

    def __init__(self, catalog: Catalog, as_of: date) -> None:
        self.catalog = catalog
        self.as_of = as_of

    # --- schedules and fares ------------------------------------------------------

    def schedule(self, origin: str, destination: str) -> list[Flight]:
        """The flights on a route. Stable across days and sites."""
        rng = _rng("schedule", origin, destination)
        km = self.catalog.distance_km(origin, destination)
        base = round(km / 760 * 60 + 35)
        flights: list[Flight] = []
        used: set[str] = set()
        for code, carrier in sorted(self.catalog.carriers.items()):
            for _ in range(rng.randint(1, 2)):
                number = f"{code}{rng.randint(100, 999)}"
                while number in used:
                    number = f"{code}{rng.randint(100, 999)}"
                used.add(number)
                stops = 0 if rng.random() < 0.75 else 1
                via: tuple[str, ...] = ()
                duration = base + rng.randint(-5, 15)
                if stops:
                    via = (rng.choice([h for h in HUBS if h not in (origin, destination)]),)
                    duration += rng.randint(70, 160)
                flights.append(
                    Flight(
                        carrier_code=code,
                        carrier_name=carrier.name,
                        number=number,
                        origin=origin,
                        destination=destination,
                        dep_minutes=rng.randrange(5 * 60, 23 * 60, 5),
                        duration=duration,
                        stops=stops,
                        via=via,
                    )
                )
        return sorted(flights, key=lambda f: f.dep_minutes)

    def fare(self, site: str, flight: Flight, depart: date) -> int:
        """Listed fare in rupees, ending in 9 like real retail fares."""
        km = self.catalog.distance_km(flight.origin, flight.destination)
        lead = max((depart - self.as_of).days, 0)
        price = 1900 + km * 2.6
        price *= 1 + 1.5 * math.exp(-lead / 6)  # close-in fares climb fast
        price *= 1.12 if depart.weekday() in (4, 6) else 1.0  # Friday and Sunday
        price *= CARRIER_FACTOR.get(flight.carrier_code, 1.0)
        price *= 0.9 if flight.stops else 1.0
        price *= SITE_FACTOR.get(site, 1.0)
        shared = _rng("fare", flight.number, depart, self.as_of)
        price *= 1 + shared.uniform(-0.06, 0.06)  # the airline's own movement
        price *= 1 + _rng("site", site, flight.number, depart, self.as_of).uniform(-0.015, 0.015)
        return int(round(price / 10) * 10 - 1)

    # --- pages --------------------------------------------------------------------

    def listings(self, site: str, origin: str, destination: str, depart: date) -> list[Listing]:
        """Every card one search page shows, in page order."""
        out: list[Listing] = []
        for flight in self.schedule(origin, destination):
            rng = _rng("extras", site, flight.number, depart, self.as_of)
            if rng.random() < 0.08:  # not every site sells every flight every day
                continue
            price: int | None = self.fare(site, flight, depart)
            if site == "skybazaar" and rng.random() < 0.03:
                price = None  # "Fare unavailable": a real-world gap the checks must catch
            offer = None
            if site == "paisaflights" and rng.random() < 0.35:
                offer = price - rng.choice([150, 200, 250, 300, 400])
            if site == "kitetravel" and rng.random() < 0.3:
                offer = price - rng.choice([100, 150, 250])
            refundable = rng.random() < 0.3
            refundable_shown: bool | None = refundable
            if site == "paisaflights" and not refundable:
                refundable_shown = None  # PaisaFlights only mentions it when it is
            baggage = 15 if rng.random() < 0.85 else 20
            seats = rng.randint(1, 8) if rng.random() < 0.25 else None
            arr = flight.arr_minutes
            ref = _ref(site, flight.number, depart, self.as_of)
            truth = CleanRecord(
                listing_id=ref,
                is_fare=True,
                carrier=flight.carrier_name,
                flight_number=flight.number,
                origin=origin,
                destination=destination,
                depart_date=depart.isoformat(),
                depart_time=_hhmm(flight.dep_minutes),
                arrive_time=_hhmm(arr % 1440),
                arrives_next_day=arr >= 1440,
                duration_minutes=flight.duration,
                stops=flight.stops,
                via=list(flight.via),
                price_inr=price,
                offer_price_inr=offer,
                refundable=refundable_shown,
                checkin_baggage_kg=baggage,
                seats_left=seats,
            )
            out.append(Listing(site, ref, flight, truth))
        if site == "kitetravel":
            rng = _rng("ad", origin, destination, depart, self.as_of)
            city = self.catalog.airports[destination].city
            nightly = rng.choice([1799, 2199, 2499, 3299])
            text = f"Sponsored · Stay at {rng.choice(HOTELS)}, {city} from ₹ {_thin(nightly)}/night"
            ref = "AD" + _ref("ad", origin, destination, depart, self.as_of)
            out.insert(min(2, len(out)), Listing(site, ref, None, _not_a_fare(ref), ad_text=text))
        return out

    def truth(
        self, site: str, origin: str, destination: str, depart: date
    ) -> dict[str, CleanRecord]:
        """The clean answer for every card on a page, keyed by the card's id."""
        return {
            item.source_ref: item.truth for item in self.listings(site, origin, destination, depart)
        }

    def render(self, site: str, origin: str, destination: str, depart: date) -> str:
        items = self.listings(site, origin, destination, depart)
        o, d = self.catalog.airports[origin], self.catalog.airports[destination]
        if site == "skybazaar":
            header = (
                f'<h1 class="search-title">{o.city} ({origin}) to {d.city} ({destination}) · '
                f"{depart.strftime('%a, %d %b %Y')}</h1>"
            )
            body = "\n".join(_skybazaar_card(i) for i in items)
            return _page("SkyBazaar", header + f'<section class="results">{body}</section>')
        if site == "paisaflights":
            header = (
                f'<div class="crumbs">{origin} ✈ {destination} | '
                f"{depart.strftime('%d/%m/%Y')}</div>"
            )
            rows = "\n".join(_paisa_row(i) for i in items)
            table = (
                "<table><tr><th>Airline</th><th>Dep</th><th>Arr</th><th>Duration</th>"
                f"<th>Stops</th><th>Fare</th><th></th></tr>{rows}</table>"
            )
            return _page("PaisaFlights", header + table)
        if site == "ghoomo":
            header = (
                f'<h2 class="ghm-head">{_hindi_city(o.city)} se {_hindi_city(d.city)} · '
                f"{depart.strftime('%d-%m-%Y')}</h2>"
            )
            rows = "\n".join(_ghoomo_row(i) for i in items)
            return _page("Ghoomo", header + f'<div class="ghm-list">{rows}</div>')
        if site == "kitetravel":
            header = (
                f'<p class="kt-search">Flights {depart.isoformat()} · '
                f"{_kite_city(o.city)} → {d.city}</p>"
            )
            lis = "\n".join(_kite_item(i) for i in items)
            return _page("Kite Travel", header + f"<ul>{lis}</ul>")
        raise KeyError(site)

    # --- HTTP -----------------------------------------------------------------------

    def handle(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        site = next((s for s in self.catalog.sites if s.host == host), None)
        if site is None:
            return httpx.Response(404, text="unknown demo host")
        if request.url.path == "/robots.txt":
            rules = "User-agent: *\nDisallow: /account\nAllow: /\n"
            if site.key == "paisaflights":
                rules += "Crawl-delay: 3\n"
            return httpx.Response(200, text=rules)
        parsed = _parse_search(site.key, str(request.url))
        if parsed is None:
            return httpx.Response(404, text="not a search page")
        origin, destination, depart = parsed
        if origin not in self.catalog.airports or destination not in self.catalog.airports:
            return httpx.Response(404, text="unknown airport")
        page = self.render(site.key, origin, destination, depart)
        return httpx.Response(200, text=page, headers={"content-type": "text/html; charset=utf-8"})

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)


# --- markup per site --------------------------------------------------------------


def _page(title: str, body: str) -> str:
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title></head>'
        f'<body><header class="nav">{title} · Login · Offers · Support</header>{body}'
        "<footer>© 2026 · Prices include taxes · Terms apply</footer></body></html>"
    )


def _skybazaar_card(item: Listing) -> str:
    f, t = item.flight, item.truth
    assert f is not None
    stops = "Non-stop" if not f.stops else f"{f.stops} stop via {', '.join(f.via)}"
    price = f"₹{t.price_inr:,}" if t.price_inr else "Fare unavailable · sold out here"
    tags = [
        "Refundable" if t.refundable else "Non-refundable",
        f"{t.checkin_baggage_kg} kg check-in",
    ]
    urgency = f'<div class="urgency">Only {t.seats_left} seats left</div>' if t.seats_left else ""
    plus = " <sup>+1</sup>" if t.arrives_next_day else ""
    return (
        f'<div class="result-card" data-offer-id="{item.source_ref}">'
        f'<div class="airline">{f.carrier_name} '
        f'<span class="fno">{f.number[:2]}-{f.number[2:]}</span></div>'
        f'<div class="times"><b>{t.depart_time}</b> → <b>{t.arrive_time}</b>{plus}</div>'
        f'<div class="meta">{f.duration // 60}h {f.duration % 60:02d}m · {stops}</div>'
        f'<div class="price">{price}</div>'
        f'<div class="tags">{" | ".join(tags)}</div>{urgency}</div>'
    )


def _paisa_row(item: Listing) -> str:
    f, t = item.flight, item.truth
    assert f is not None
    stops = "0 stops" if not f.stops else f"{f.stops} stop ({', '.join(f.via)})"
    fare = f"Rs. {t.price_inr}/-"
    if t.offer_price_inr:
        cashback = t.price_inr - t.offer_price_inr
        fare += (
            f"<br><em>Cashback ₹{cashback} with code PAISA{cashback} "
            f"(you pay ₹{t.offer_price_inr:,})</em>"
        )
    perks = ["🔥 Free meal" if _rng("meal", item.source_ref).random() < 0.4 else "Saver fare"]
    if t.refundable:
        perks.append("Fully refundable")
    perks.append(f"Check-in {t.checkin_baggage_kg}kg")
    if t.seats_left:
        perks.append(f"{t.seats_left} left")
    return (
        f'<tr class="fare" data-fare-key="{item.source_ref}">'
        f"<td>{f.carrier_name.upper()}<br><small>{f.number[:2]} {f.number[2:]}</small></td>"
        f"<td>{_ampm(f.dep_minutes)}</td><td>{_ampm(f.arr_minutes)}</td>"
        f"<td>{f.duration} mins</td><td>{stops}</td><td>{fare}</td>"
        f"<td>{' | '.join(perks)}</td></tr>"
    )


def _kite_item(item: Listing) -> str:
    if item.flight is None:
        text = html.escape(item.ad_text)
        return f'<li class="kt-offer sponsored" data-ref="{item.source_ref}">{text}</li>'
    f, t = item.flight, item.truth
    short = f.carrier_name.split()[0]
    arr = f.arr_minutes
    plus = " (+1)" if arr >= 1440 else ""
    stops = "Direct" if not f.stops else f"{f.stops} stop · via {', '.join(f.via)}"
    parts = [
        f"{short} · {f.number}",
        f"Departs {_hhmm(f.dep_minutes).replace(':', '')} hrs, arrives "
        f"{_hhmm(arr % 1440).replace(':', '')} hrs{plus}",
        f"{f.duration // 60}:{f.duration % 60:02d} hrs",
        stops,
        f"₹ {_thin(t.price_inr)}",
        f"Cabin 7kg + Check-in {t.checkin_baggage_kg}kg",
        "Refundable" if t.refundable else "Non-refundable",
    ]
    if t.offer_price_inr:
        parts.append(f"coupon KITE{t.price_inr - t.offer_price_inr} → ₹ {_thin(t.offer_price_inr)}")
    if t.seats_left:
        parts.append(f"hurry, {t.seats_left} seats left")
    return f'<li class="kt-offer" data-ref="{item.source_ref}">{" · ".join(parts)}</li>'


def _ghoomo_row(item: Listing) -> str:
    f, t = item.flight, item.truth
    assert f is not None
    arr = f.arr_minutes
    stops = "Seedhi flight" if not f.stops else f"{f.stops} stop, {', '.join(f.via)} mein rukegi"
    parts = [
        f"{f.carrier_name} {f.number[:2]}-{f.number[2:]}",
        f"Ravana {_hhmm(f.dep_minutes).replace(':', 'h')} → Pahunch "
        f"{_hhmm(arr % 1440).replace(':', 'h')}" + (" (agle din)" if arr >= 1440 else ""),
        f"Safar: {f.duration // 60} ghante {f.duration % 60} min",
        stops,
        f"Kiraya ₹{t.price_inr:,} (sab taxes milake)",
        f"Bag: {t.checkin_baggage_kg} kilo",
        f"Refund: {'haan' if t.refundable else 'nahi'}",
    ]
    if t.seats_left:
        parts.append(f"sirf {t.seats_left} seat bachi hain")
    return f'<div class="ghm-row" data-id="{item.source_ref}">{" | ".join(parts)}</div>'


def _hindi_city(city: str) -> str:
    return {"Delhi": "Dilli", "Mumbai": "Mumbai", "Kolkata": "Kolkata"}.get(city, city)


# --- helpers ----------------------------------------------------------------------


def _not_a_fare(ref: str) -> CleanRecord:
    return CleanRecord(
        listing_id=ref,
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


def _hhmm(minutes: int) -> str:
    minutes %= 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _ampm(minutes: int) -> str:
    next_day = minutes >= 1440
    minutes %= 1440
    h, m = divmod(minutes, 60)
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}" + (" (+1)" if next_day else "")


def _thin(amount: int) -> str:
    """4599 -> '4 599' with a narrow no-break space."""
    return f"{amount:,}".replace(",", NNBSP)


def _kite_city(city: str) -> str:
    return "New Delhi" if city == "Delhi" else city


def _parse_search(site: str, url: str) -> tuple[str, str, date] | None:
    parts = urlsplit(url)
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    try:
        if site == "skybazaar" and parts.path == "/flights/search":
            return query["from"], query["to"], date.fromisoformat(query["date"])
        if site == "paisaflights" and parts.path.startswith("/search/"):
            _, _, route, day = parts.path.split("/")
            origin, destination = route.split("-")
            return origin, destination, date.fromisoformat(day)
        if site == "ghoomo" and parts.path.startswith("/udaan/"):
            _, _, origin, destination = parts.path.split("/")
            return origin, destination, date.fromisoformat(query["din"])
        if site == "kitetravel" and parts.path == "/f":
            return query["o"], query["d"], date.fromisoformat(query["on"])
    except (KeyError, ValueError):
        return None
    return None


def depart_dates(as_of: date, offsets: list[int]) -> list[date]:
    return [as_of + timedelta(days=k) for k in offsets]

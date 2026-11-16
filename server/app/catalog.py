"""Typed access to the JSON files in ``app/config``.

Everything editorial (which sites, which routes, which carriers, who sees what) is
data, so adding a site or a user is a JSON edit and never a code change.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from app.core.errors import ConfigError


@dataclass(frozen=True)
class Site:
    key: str
    name: str
    base_url: str
    search_path: str
    card_selector: str
    id_attr: str
    context_selector: str
    min_delay_seconds: float = 2.0
    enabled: bool = True

    def search_url(self, origin: str, destination: str, depart_date: str) -> str:
        path = self.search_path.format(
            origin=origin, destination=destination, depart_date=depart_date
        )
        return self.base_url.rstrip("/") + path

    @property
    def host(self) -> str:
        return self.base_url.split("://", 1)[-1].split("/", 1)[0]


@dataclass(frozen=True)
class Airport:
    iata: str
    city: str
    state: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Carrier:
    code: str
    name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class AccessRule:
    email: str
    name: str
    origins: tuple[str, ...]


@dataclass
class Catalog:
    """All config files, loaded once."""

    sites: list[Site]
    routes: list[tuple[str, str]]
    depart_offsets_days: list[int]
    airports: dict[str, Airport]
    carriers: dict[str, Carrier]
    access: list[AccessRule] = field(default_factory=list)

    @classmethod
    def load(cls, config_dir: Path) -> Catalog:
        sites = [Site(**s) for s in _read(config_dir / "sites.json")["sites"]]
        plan = _read(config_dir / "search_plan.json")
        airports = {
            a["iata"]: Airport(**a) for a in _read(config_dir / "airports.json")["airports"]
        }
        carriers = {}
        for c in _read(config_dir / "carriers.json")["carriers"]:
            carriers[c["code"]] = Carrier(c["code"], c["name"], tuple(c.get("aliases", [])))
        access = [
            AccessRule(u["email"].lower(), u.get("name", u["email"]), tuple(u["origins"]))
            for u in _read(config_dir / "user_access.json")["users"]
        ]
        catalog = cls(
            sites=sites,
            routes=[(o, d) for o, d in plan["routes"]],
            depart_offsets_days=list(plan["depart_offsets_days"]),
            airports=airports,
            carriers=carriers,
            access=access,
        )
        catalog.check()
        return catalog

    def check(self) -> None:
        """Fail early on a typo in the config, not halfway through a scrape."""
        for origin, destination in self.routes:
            for code in (origin, destination):
                if code not in self.airports:
                    raise ConfigError(f"Route uses {code}, which is not in airports.json.")
        for rule in self.access:
            for origin in rule.origins:
                if origin != "*" and origin not in self.airports:
                    raise ConfigError(f"{rule.email} is given {origin}, not in airports.json.")
        keys = [s.key for s in self.sites]
        if len(keys) != len(set(keys)):
            raise ConfigError("Two sites in sites.json share a key.")

    @property
    def enabled_sites(self) -> list[Site]:
        return [s for s in self.sites if s.enabled]

    def site(self, key: str) -> Site:
        for s in self.sites:
            if s.key == key:
                return s
        raise ConfigError(f"No site {key!r} in sites.json.")

    @cached_property
    def _alias_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        for carrier in self.carriers.values():
            for spelling in (carrier.code, carrier.name, *carrier.aliases):
                index[_norm(spelling)] = carrier.code
        return index

    def carrier_code(self, name_or_code: str | None) -> str | None:
        """Map any spelling of a carrier ("KESTREL AIR", "Kestrel", "KS") to its code."""
        if not name_or_code:
            return None
        return self._alias_index.get(_norm(name_or_code))

    def carrier_spellings(self) -> list[tuple[str, str]]:
        """(spelling, code) pairs, longest first, for matching inside free text."""
        pairs = [(s, c) for s, c in self._alias_index.items() if len(s) > 2]
        return sorted(pairs, key=lambda p: -len(p[0]))

    def distance_km(self, origin: str, destination: str) -> int:
        """Great-circle distance between two airports, rounded to the kilometre."""
        a, b = self.airports[origin], self.airports[destination]
        lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
        h = (
            math.sin((lat2 - lat1) / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        )
        return round(2 * 6371 * math.asin(math.sqrt(h)))

    def origins_for(self, email: str | None) -> set[str] | None:
        """Airports this person may see; None when the email is not in user_access.json."""
        if not email:
            return None
        for rule in self.access:
            if rule.email == email.strip().lower():
                if "*" in rule.origins:
                    return set(self.airports)
                return set(rule.origins)
        return None


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("-", " ").split())


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Missing config file {path}.") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path.name} is not valid JSON: {exc}") from exc

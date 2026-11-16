"""A polite HTTP fetcher: robots.txt first, one request at a time per host, retries.

This is the part people skip and then get blocked. Every request:

1. checks the host's robots.txt (fetched once per host and cached),
2. waits until the host's delay has passed (the larger of our minimum, the site's own
   ``min_delay_seconds`` and any ``Crawl-delay`` in robots.txt),
3. retries 429 and 5xx with exponential backoff, honouring ``Retry-After``.

The clock and sleep are injectable so tests can check the delays without waiting.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from urllib.robotparser import RobotFileParser

import httpx

from app.core.errors import ScrapeError

logger = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class Fetcher:
    def __init__(
        self,
        client: httpx.Client,
        *,
        user_agent: str,
        min_delay_seconds: float = 2.0,
        max_retries: int = 3,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._user_agent = user_agent
        self._min_delay = min_delay_seconds
        self._max_retries = max_retries
        self._clock = clock
        self._sleep = sleep
        self._robots: dict[str, RobotFileParser] = {}
        self._last_request: dict[str, float] = {}
        self.requests_made = 0

    def get(self, url: str, *, site_delay_seconds: float = 0.0) -> str:
        """Fetch a page's HTML, or raise :class:`ScrapeError`."""
        host = httpx.URL(url).host
        robots = self._robots_for(url)
        if not robots.can_fetch(self._user_agent, url):
            raise ScrapeError(f"robots.txt on {host} does not allow {url}")
        crawl_delay = robots.crawl_delay(self._user_agent) or 0
        delay = max(self._min_delay, site_delay_seconds, float(crawl_delay))

        for attempt in range(self._max_retries + 1):
            self._wait_turn(host, delay)
            try:
                response = self._client.get(url, headers={"User-Agent": self._user_agent})
            except httpx.HTTPError as exc:
                if attempt == self._max_retries:
                    raise ScrapeError(f"Could not reach {url}: {exc}") from exc
                self._sleep(2**attempt)
                continue
            self.requests_made += 1
            if response.status_code == 200:
                return response.text
            if response.status_code in RETRY_STATUS and attempt < self._max_retries:
                wait = _retry_after(response) or 2**attempt
                logger.warning("%s returned %s; retrying in %ss", url, response.status_code, wait)
                self._sleep(wait)
                continue
            raise ScrapeError(f"{url} returned HTTP {response.status_code}")
        raise ScrapeError(f"Gave up on {url}")  # pragma: no cover

    def _robots_for(self, url: str) -> RobotFileParser:
        parts = httpx.URL(url)
        key = f"{parts.scheme}://{parts.host}"
        if key not in self._robots:
            parser = RobotFileParser()
            try:
                response = self._client.get(
                    f"{key}/robots.txt", headers={"User-Agent": self._user_agent}
                )
                if response.status_code >= 400:
                    parser.parse([])  # no robots.txt: everything is allowed
                else:
                    parser.parse(response.text.splitlines())
            except httpx.HTTPError:
                parser.parse([])
            self._robots[key] = parser
        return self._robots[key]

    def _wait_turn(self, host: str, delay: float) -> None:
        last = self._last_request.get(host)
        if last is not None:
            remaining = delay - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[host] = self._clock()


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None

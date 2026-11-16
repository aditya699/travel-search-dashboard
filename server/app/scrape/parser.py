"""Turn a search page into cards: one block of text per result.

The parser does not try to understand prices or times. It only cuts the page into
results with the site's CSS selector, so a new site needs three selectors in
``sites.json`` and nothing else. Making sense of the text is the cleaning layer's job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from app.catalog import Site


@dataclass(frozen=True)
class Card:
    source_ref: str
    text: str


def parse_page(page_html: str, site: Site) -> tuple[str, list[Card]]:
    """Return the page header text and the result cards, in page order."""
    soup = BeautifulSoup(page_html, "html.parser")
    header = soup.select_one(site.context_selector)
    context = _text(header) if header else ""
    cards = []
    for position, node in enumerate(soup.select(site.card_selector)):
        ref = node.get(site.id_attr) or f"pos{position}"
        text = _text(node)
        if text:
            cards.append(Card(source_ref=str(ref), text=text))
    return context, cards


def _text(node) -> str:
    """Visible text with a separator between elements, ASCII whitespace squeezed.

    Unicode spaces (the narrow no-break space inside "₹ 4 599") are kept, because
    they are part of what the cleaner has to cope with.
    """
    raw = node.get_text(" | ", strip=True)
    return _SPACES.sub(" ", raw).strip()


_SPACES = re.compile(r"[ \t\r\n]+")

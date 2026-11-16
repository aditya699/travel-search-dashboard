"""Write one search page per demo site to ../samples/, so you can see the mess.

    uv run python scripts/make_samples.py

Open the files in a browser, or read them as text: the same flights, four formats.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog import Catalog
from app.core.config import CONFIG_DIR
from app.scrape.demo_sites import DemoSites

AS_OF = date(2026, 11, 16)
DEPART = date(2026, 11, 25)


def main() -> None:
    catalog = Catalog.load(CONFIG_DIR)
    sites = DemoSites(catalog, AS_OF)
    out = Path(__file__).resolve().parents[2] / "samples"
    out.mkdir(exist_ok=True)
    for site in catalog.sites:
        page = sites.render(site.key, "DEL", "BOM", DEPART)
        path = out / f"{site.key}-DEL-BOM-{DEPART.isoformat()}.html"
        path.write_text(page.replace("</div><div", "</div>\n<div"), encoding="utf-8")
        print(f"wrote {path.name}")


if __name__ == "__main__":
    main()

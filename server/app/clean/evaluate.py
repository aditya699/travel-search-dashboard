"""Score the cleaner against the demo sites' ground truth, field by field.

The demo sites know the right answer for every card they render, so on demo data you
can measure the cleaner instead of eyeballing it: run ``clean`` with
``LLM_PROVIDER=fake``, then ``eval``; switch to ``anthropic`` (try two models), clean
again into a fresh DATA_DIR, ``eval`` again, and compare. That comparison is the
paragraph an interviewer wants to hear.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.catalog import Catalog
from app.clean.schema import FIELDS_SCORED
from app.core.config import Settings
from app.core.errors import AppError
from app.scrape.demo_sites import DemoSites


@dataclass
class EvalReport:
    listings: int = 0
    exact_rows: int = 0
    correct: Counter = field(default_factory=Counter)
    examples: list[dict[str, Any]] = field(default_factory=list)

    def field_accuracy(self) -> dict[str, float]:
        if not self.listings:
            return {}
        return {name: self.correct[name] / self.listings for name in FIELDS_SCORED}

    @property
    def row_accuracy(self) -> float:
        return self.exact_rows / self.listings if self.listings else 0.0


def evaluate(settings: Settings, catalog: Catalog, max_examples: int = 8) -> EvalReport:
    if settings.scrape_mode != "demo":
        raise AppError("eval needs ground truth, which only the demo sites have.")
    rows = []
    for path in sorted(settings.clean_dir.glob("as_of=*/*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            rows.extend(json.loads(line) for line in handle if line.strip())
    if not rows:
        raise AppError("Nothing cleaned yet. Run `python -m app.cli demo` first.")

    report = EvalReport()
    pages: dict[tuple, dict] = {}
    for row in rows:
        if row.get("model") is None:  # cleaning failed; counts as all wrong
            report.listings += 1
            continue
        key = (
            row["as_of"],
            row["site"],
            row["searched_origin"],
            row["searched_destination"],
            row["searched_depart_date"],
        )
        if key not in pages:
            sites = DemoSites(catalog, date.fromisoformat(row["as_of"]))
            pages[key] = sites.truth(row["site"], key[2], key[3], date.fromisoformat(key[4]))
        truth = pages[key].get(row["source_ref"])
        if truth is None:
            continue
        report.listings += 1
        expected = truth.model_dump()
        wrong = []
        for name in FIELDS_SCORED:
            got, want = row.get(name), expected.get(name)
            if name == "carrier":
                got, want = catalog.carrier_code(got), catalog.carrier_code(want)
            if _same(got, want):
                report.correct[name] += 1
            else:
                wrong.append({"field": name, "got": got, "want": want})
        if not wrong:
            report.exact_rows += 1
        elif len(report.examples) < max_examples:
            report.examples.append({"text": row["card_text"], "wrong": wrong})
    return report


def _same(got: Any, want: Any) -> bool:
    if isinstance(want, list) or isinstance(got, list):
        return list(got or []) == list(want or [])
    if want is None or got is None:
        return got is None and want is None
    return str(got).strip().upper() == str(want).strip().upper()

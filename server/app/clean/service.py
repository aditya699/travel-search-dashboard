"""The cleaning layer: raw cards in, validated rows out.

For every raw listing:

1. look it up in the cache by ``content_hash`` (same site, same search, same text);
   a hit costs nothing, so re-running a day, or re-validating after a rules change,
   never pays for the LLM twice;
2. send the misses to the LLM in batches (``CLEAN_BATCH_SIZE`` per request);
3. run the deterministic checks in :mod:`app.clean.validate`;
4. write ``data/clean/as_of=YYYY-MM-DD/<site>.jsonl`` with a status for each row:
   ``ok`` (goes to the fact table), ``not_fare`` (ads) or ``rejected`` (quarantine).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.catalog import Catalog
from app.clean.schema import CleanBatch, CleanRecord
from app.clean.validate import validate
from app.core.config import Settings
from app.core.errors import LLMError
from app.llm.base import LLMClient

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "llm" / "prompts" / "clean_listings.md"


@dataclass
class CleanReport:
    listings: int = 0
    cache_hits: int = 0
    llm_calls: int = 0
    status: Counter = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)


def read_raw(settings: Settings, as_of: list[str] | None = None) -> list[dict[str, Any]]:
    """Every raw listing in the lake, optionally only for some scrape dates."""
    rows: list[dict[str, Any]] = []
    for path in sorted(settings.raw_dir.glob("as_of=*/*.jsonl")):
        day = path.parent.name.removeprefix("as_of=")
        if as_of and day not in as_of:
            continue
        with path.open(encoding="utf-8") as handle:
            rows.extend(json.loads(line) for line in handle if line.strip())
    return rows


class CleaningService:
    def __init__(self, settings: Settings, catalog: Catalog, llm: LLMClient) -> None:
        self.settings = settings
        self.catalog = catalog
        self.llm = llm
        self.system = PROMPT_PATH.read_text(encoding="utf-8")
        self.cache_path = settings.cache_dir / "clean_cache.jsonl"

    def run(self, as_of: list[str] | None = None) -> CleanReport:
        return asyncio.run(self.arun(as_of))

    async def arun(self, as_of: list[str] | None = None) -> CleanReport:
        raw = read_raw(self.settings, as_of)
        report = CleanReport(listings=len(raw))
        cache = self._load_cache()

        todo: dict[str, dict[str, Any]] = {}
        for row in raw:
            if row["content_hash"] in cache:
                report.cache_hits += 1
            else:
                todo.setdefault(row["content_hash"], row)

        if todo:
            logger.info("Cleaning %d new listings with %s", len(todo), self.llm.name)
            fresh = await self._clean_batches(list(todo.values()), report)
            self._append_cache(fresh)
            cache.update(fresh)

        by_partition: dict[tuple[str, str], list[str]] = defaultdict(list)
        for row in raw:
            entry = cache.get(row["content_hash"])
            if entry is None:
                out = {"status": "rejected", "reasons": ["cleaning failed; re-run clean"]}
                out.update(_identity(row))
                out["model"] = None
            else:
                record = CleanRecord.model_validate(entry["record"])
                verdict = validate(record, row, self.catalog)
                out = record.model_dump()
                out.update(_identity(row))
                out.update(
                    status=verdict.status,
                    reasons=verdict.reasons,
                    carrier_code=verdict.carrier_code,
                    model=entry["model"],
                )
            report.status[out["status"]] += 1
            by_partition[(row["as_of"], row["site"])].append(json.dumps(out, ensure_ascii=False))

        for (day, site), lines in by_partition.items():
            folder = self.settings.clean_dir / f"as_of={day}"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{site}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report

    async def _clean_batches(
        self, rows: list[dict[str, Any]], report: CleanReport
    ) -> dict[str, dict[str, Any]]:
        size = max(1, self.settings.clean_batch_size)
        batches = [rows[i : i + size] for i in range(0, len(rows), size)]
        results = await asyncio.gather(
            *(self._clean_one(batch) for batch in batches), return_exceptions=True
        )
        fresh: dict[str, dict[str, Any]] = {}
        for batch, result in zip(batches, results, strict=True):
            report.llm_calls += 1
            if isinstance(result, LLMError):
                report.errors.append(str(result))
                logger.error("Batch of %d failed: %s", len(batch), result)
                continue
            if isinstance(result, BaseException):
                raise result
            returned = {r.listing_id: r for r in result.records}
            for row in batch:
                record = returned.get(row["content_hash"])
                if record is None:
                    report.errors.append(f"model skipped listing {row['content_hash']}")
                    continue
                fresh[row["content_hash"]] = {
                    "content_hash": row["content_hash"],
                    "model": self.llm.name,
                    "record": record.model_dump(),
                }
        return fresh

    async def _clean_one(self, batch: list[dict[str, Any]]) -> CleanBatch:
        sites = {s.key: s.name for s in self.catalog.sites}
        payload = {
            "listings": [
                {
                    "id": row["content_hash"],
                    "site": sites.get(row["site"], row["site"]),
                    "searched": {
                        "origin": row["origin"],
                        "destination": row["destination"],
                        "depart_date": row["depart_date"],
                    },
                    "page_header": row["page_context"],
                    "text": row["card_text"],
                }
                for row in batch
            ]
        }
        content = json.dumps(payload, ensure_ascii=False)
        return await self.llm.structured(system=self.system, content=content, schema=CleanBatch)

    def _load_cache(self) -> dict[str, dict[str, Any]]:
        cache: dict[str, dict[str, Any]] = {}
        if self.cache_path.exists():
            with self.cache_path.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        entry = json.loads(line)
                        cache[entry["content_hash"]] = entry
        return cache

    def _append_cache(self, fresh: dict[str, dict[str, Any]]) -> None:
        if not fresh:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("a", encoding="utf-8") as handle:
            for entry in fresh.values():
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _identity(row: dict[str, Any]) -> dict[str, Any]:
    """Columns that come from the scrape, not from the model."""
    return {
        "listing_id": row["listing_id"],
        "content_hash": row["content_hash"],
        "site": row["site"],
        "source_ref": row["source_ref"],
        "as_of": row["as_of"],
        "searched_origin": row["origin"],
        "searched_destination": row["destination"],
        "searched_depart_date": row["depart_date"],
        "card_text": row["card_text"],
    }

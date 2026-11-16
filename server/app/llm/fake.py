"""An offline stand-in for Claude: answers the cleaning call with the regex rules.

Used by ``LLM_PROVIDER=fake`` and by the tests. It implements the same
:class:`app.llm.base.LLMClient` interface, so the cleaning service cannot tell the
difference.
"""

from __future__ import annotations

import json

from app.catalog import Catalog
from app.clean.rules import clean_listing
from app.clean.schema import CleanBatch
from app.llm.base import T


class FakeLLM:
    name = "fake-rules"

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self.calls = 0

    async def structured(self, *, system: str, content: str, schema: type[T]) -> T:
        self.calls += 1
        if schema is not CleanBatch:
            raise NotImplementedError(f"FakeLLM only knows how to clean, not {schema.__name__}")
        listings = json.loads(content)["listings"]
        records = [clean_listing(item, self._catalog) for item in listings]
        return schema(records=records)

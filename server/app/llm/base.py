"""The interface every language-model backend implements.

The cleaning service depends on :class:`LLMClient`, never on a vendor SDK, so you can
swap providers, or run :class:`app.llm.fake.FakeLLM` offline, without touching it.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    """The one call the cleaner needs."""

    name: str

    async def structured(self, *, system: str, content: str, schema: type[T]) -> T:
        """Return the model's answer parsed into ``schema`` (a Pydantic model)."""
        ...

"""Claude implementation of :class:`app.llm.base.LLMClient`.

:meth:`AnthropicLLM.structured` uses structured outputs (``messages.parse`` with a
Pydantic ``output_format``), so the reply is validated JSON in the schema's shape, not
prose to parse with regexes.

It opts into server-side refusal fallbacks (``fallbacks="default"``): if the main
model declines, the API retries on a fallback model inside the same request.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import anthropic
from anthropic import AsyncAnthropic

from app.core.errors import LLMError, LLMRefusalError
from app.llm.base import T

logger = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 16000


class AnthropicLLM:
    """Async Claude client with a concurrency cap."""

    def __init__(
        self,
        *,
        model: str,
        effort: str = "low",
        api_key: str | None = None,
        max_concurrency: int = 4,
    ) -> None:
        # api_key=None lets the SDK find credentials itself (ANTHROPIC_API_KEY, etc.).
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._effort = effort
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self.name = model

    async def structured(self, *, system: str, content: str, schema: type[T]) -> T:
        """Call Claude with structured outputs and return a validated ``schema``."""
        async with self._semaphore:
            response = await self._call(
                self._client.beta.messages.parse,
                model=self._model,
                max_tokens=MAX_TOKENS,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                output_format=schema,
                output_config={"effort": self._effort},
                system=system,
                messages=[{"role": "user", "content": content}],
            )
        if response.stop_reason == "refusal":
            details = response.stop_details
            explanation = getattr(details, "explanation", None) or "no explanation given"
            raise LLMRefusalError(f"Claude declined this batch: {explanation}")
        if response.stop_reason == "max_tokens":
            raise LLMError("Claude ran out of output tokens; lower CLEAN_BATCH_SIZE.")
        parsed = response.parsed_output
        if parsed is None:
            raise LLMError(f"Claude returned no {schema.__name__} (request {response.id}).")
        usage = response.usage
        logger.debug("clean batch: %s in / %s out tokens", usage.input_tokens, usage.output_tokens)
        return parsed

    @staticmethod
    async def _call(method: Any, **kwargs: Any) -> Any:
        """Run an SDK call and turn SDK errors into :class:`LLMError`.

        The SDK already retries 408/409/429/5xx and connection errors; anything that
        reaches us here has used up those retries.
        """
        try:
            return await method(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise LLMError(
                "Anthropic rejected the API key. Set ANTHROPIC_API_KEY in server/.env, "
                "or set LLM_PROVIDER=fake to run without one."
            ) from exc
        except anthropic.NotFoundError as exc:
            raise LLMError(f"Model or endpoint not found: {exc.message}") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Rate limited by Anthropic; lower MAX_CONCURRENCY.") from exc
        except anthropic.BadRequestError as exc:
            raise LLMError(f"Claude rejected the request: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Could not reach the Anthropic API; check your network.") from exc

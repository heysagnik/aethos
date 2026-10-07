"""LLM access (Groq) with usage metering and strict output parsing."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import groq
from django.conf import settings
from pydantic import ValidationError

from core.schemas import ReviewOutput

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_MILLION = Decimal(1_000_000)


class LLMOutputError(ValueError):
    """The model returned something that is not a valid ReviewOutput."""


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    tokens_cached: int
    duration_ms: int
    truncated: bool = False


class LLMClient(Protocol):
    def complete_json(
        self, *, model: str, system: str, user: str, max_tokens: int
    ) -> LLMResult: ...


class GroqLLM:
    def __init__(self) -> None:
        self._client = groq.Groq(
            api_key=settings.GROQ_API_KEY, timeout=settings.LLM_TIMEOUT_SECONDS, max_retries=1
        )

    def complete_json(self, *, model: str, system: str, user: str, max_tokens: int) -> LLMResult:
        started = time.monotonic()
        response = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=max_tokens,
            temperature=0.1,
        )
        choice = response.choices[0]
        usage = response.usage
        details = getattr(usage, "prompt_tokens_details", None) if usage else None
        return LLMResult(
            text=choice.message.content or "",
            model=model,
            tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
            tokens_out=getattr(usage, "completion_tokens", 0) or 0,
            tokens_cached=getattr(details, "cached_tokens", 0) or 0,
            duration_ms=int((time.monotonic() - started) * 1000),
            truncated=choice.finish_reason == "length",
        )


def get_llm() -> LLMClient:
    """Factory used by the pipeline. Tests replace this with a fake."""
    return GroqLLM()


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> Decimal:
    prices = settings.LLM_PRICES.get(model)
    if prices is None:
        return Decimal(0)
    price_in, price_out = prices
    return (price_in * tokens_in + price_out * tokens_out) / _MILLION


def parse_review(text: str) -> ReviewOutput:
    cleaned = _FENCE_RE.sub("", text.strip())
    try:
        return ReviewOutput.model_validate(json.loads(cleaned))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise LLMOutputError(str(exc)[:500]) from exc

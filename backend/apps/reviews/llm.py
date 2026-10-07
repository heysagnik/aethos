"""LLM access (NVIDIA NIM) with usage metering and strict output parsing."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import httpx
from django.conf import settings
from pydantic import ValidationError

from core.schemas import ReviewOutput

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_MILLION = Decimal(1_000_000)


class LLMRequestError(RuntimeError):
    """The model API rejected or failed the request."""


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


class NimLLM:
    """Chat completions on NVIDIA NIM (OpenAI-compatible)."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=settings.LLM_TIMEOUT_SECONDS)

    def complete_json(self, *, model: str, system: str, user: str, max_tokens: int) -> LLMResult:
        started = time.monotonic()
        response = self._client.post(
            f"{settings.NVIDIA_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.NVIDIA_API_KEY}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": max_tokens,
                "temperature": 0.1,
            },
        )
        if response.status_code >= 400:
            raise LLMRequestError(f"NIM returned {response.status_code}: {response.text[:300]}")
        data = response.json()
        choice = data["choices"][0]
        usage = data.get("usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        return LLMResult(
            text=choice["message"].get("content") or "",
            model=model,
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            tokens_cached=int(details.get("cached_tokens") or 0),
            duration_ms=int((time.monotonic() - started) * 1000),
            truncated=choice.get("finish_reason") == "length",
        )


def get_llm() -> LLMClient:
    """Factory used by the pipeline. Tests replace this with a fake."""
    return NimLLM()


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> Decimal:
    prices = settings.LLM_PRICES.get(model)
    if prices is None:
        return Decimal(0)
    price_in, price_out = prices
    return (price_in * tokens_in + price_out * tokens_out) / _MILLION


def parse_review(text: str) -> ReviewOutput:
    cleaned = _FENCE_RE.sub("", _THINK_RE.sub("", text).strip())
    try:
        return ReviewOutput.model_validate(json.loads(cleaned))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise LLMOutputError(str(exc)[:500]) from exc

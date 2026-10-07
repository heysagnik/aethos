"""Step delivery: QStash in production, direct calls for local development and tests."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from django.conf import settings
from qstash import QStash

logger = logging.getLogger(__name__)

STEP_RETRIES = 3
_force_inline: ContextVar[bool] = ContextVar("aethos_force_inline", default=False)


@contextmanager
def inline_steps() -> Iterator[None]:
    """Run the whole chain in-process (management commands such as `compare`)."""
    token = _force_inline.set(True)
    try:
        yield
    finally:
        _force_inline.reset(token)


def _dedup_id(step: str, key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "-", f"{step}-{key}")[:128]


def enqueue(step: str, payload: dict[str, Any], dedup_key: str) -> None:
    if settings.QUEUE_MODE == "inline" or _force_inline.get():
        from apps.reviews import pipeline

        pipeline.run_step(step, payload)
        return
    client = QStash(settings.QSTASH_TOKEN, base_url=settings.QSTASH_URL or None)
    client.message.publish_json(
        url=f"{settings.APP_BASE_URL}/api/steps/{step}",
        body=payload,
        retries=STEP_RETRIES,
        deduplication_id=_dedup_id(step, dedup_key),
    )

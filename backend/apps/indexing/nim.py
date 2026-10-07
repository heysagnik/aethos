"""NVIDIA NIM embeddings (hosted, OpenAI-compatible) for code chunks."""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx
from django.conf import settings

from core import vectors

# The model reads far more, but code chunks are short; this also bounds request size.
MAX_TEXT_CHARS = 6000
RETRIES = 3

EmbedFn = Callable[[list[str], str], list[list[float]]]


class EmbeddingError(Exception):
    """The embeddings service failed or returned something unusable."""


def chunk_embedding_text(path: str, qualified_name: str, text: str) -> str:
    return f"{path} {qualified_name}\n{text}".strip()[:MAX_TEXT_CHARS]


def is_configured() -> bool:
    return bool(settings.NVIDIA_API_KEY)


def embed_texts(
    texts: list[str], input_type: str = "passage", *, client: httpx.Client | None = None
) -> list[list[float]]:
    """Unit-length embeddings, one per text. `input_type` is "passage" (stored) or "query"."""
    if not texts:
        return []
    http = client or httpx.Client(timeout=60.0)
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            response = http.post(
                f"{settings.NVIDIA_BASE_URL}/embeddings",
                headers={"Authorization": f"Bearer {settings.NVIDIA_API_KEY}"},
                json={
                    "model": settings.EMBEDDING_MODEL,
                    "input": texts,
                    "input_type": input_type,
                    "encoding_format": "float",
                    "truncate": "END",
                },
            )
            if response.status_code == 429 or response.status_code >= 500:
                last = EmbeddingError(f"NIM returned {response.status_code}")
                time.sleep(2**attempt)
                continue
            if response.status_code >= 400:
                raise EmbeddingError(f"NIM returned {response.status_code}: {response.text[:300]}")
            rows = sorted(response.json()["data"], key=lambda row: row["index"])
        except httpx.TransportError as exc:
            last = exc
            time.sleep(2**attempt)
            continue
        except (KeyError, ValueError) as exc:
            raise EmbeddingError(f"Unexpected NIM response: {exc}") from exc
        out = [[float(x) for x in row["embedding"]] for row in rows]
        if len(out) != len(texts):
            raise EmbeddingError(f"Expected {len(texts)} embeddings, got {len(out)}")
        for vec in out:
            if len(vec) != settings.EMBEDDING_DIM:
                raise EmbeddingError(
                    f"Expected {settings.EMBEDDING_DIM} dimensions, got {len(vec)}"
                )
        return [vectors.normalize(vec) for vec in out]
    raise EmbeddingError(f"Embeddings failed after {RETRIES} attempts: {last}")

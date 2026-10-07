"""Embed code chunks with BAAI bge-base-en-v1.5, running locally inside the indexer job."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from core import vectors

MODEL_NAME = "BAAI/bge-base-en-v1.5"
EMBEDDING_DIM = 768
# The model reads 512 tokens; code averages ~3 characters per token, so stay under that.
MAX_TEXT_CHARS = 1400
BATCH_SIZE = 32
PRECISION = 5

Embed = Callable[[list[str]], list[list[float]]]


def chunk_embedding_text(path: str, qualified_name: str, text: str) -> str:
    return f"{path} {qualified_name}\n{text}".strip()[:MAX_TEXT_CHARS]


def load_model() -> Embed | None:
    """The local BGE model, or None (with a warning) if fastembed is unavailable."""
    try:
        from fastembed import TextEmbedding
    except ImportError:
        print("fastembed is not installed; uploading without embeddings.", file=sys.stderr)
        return None
    model = TextEmbedding(model_name=MODEL_NAME)

    def embed(texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in row] for row in model.embed(texts, batch_size=BATCH_SIZE)]

    return embed


def attach_embeddings(payloads: list[dict[str, Any]], embed: Embed) -> int:
    """Add an "embedding" to every chunk of the given file payloads. Returns how many."""
    slots: list[dict[str, Any]] = []
    texts: list[str] = []
    for payload in payloads:
        symbols = payload["symbols"]
        for chunk in payload["chunks"]:
            index = chunk["symbol_index"]
            name = symbols[index]["qualified_name"] if index is not None else ""
            slots.append(chunk)
            texts.append(chunk_embedding_text(payload["path"], name, chunk["text"]))
    for start in range(0, len(texts), BATCH_SIZE * 4):
        batch = embed(texts[start : start + BATCH_SIZE * 4])
        for chunk, vec in zip(slots[start : start + len(batch)], batch, strict=True):
            if len(vec) != EMBEDDING_DIM:
                raise ValueError(f"Expected {EMBEDDING_DIM} dimensions, got {len(vec)}")
            chunk["embedding"] = [round(x, PRECISION) for x in vectors.normalize(vec)]
    return len(texts)

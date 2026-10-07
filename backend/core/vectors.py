"""Small vector helpers (pure)."""

from __future__ import annotations

import json
import math


def normalize(vector: list[float]) -> list[float]:
    """L2-normalize. Truncated embeddings are not guaranteed to be unit length."""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return list(vector)
    return [x / norm for x in vector]


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def to_text(vector: list[float]) -> str:
    """pgvector's text format, which SQLite stores as plain text too."""
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def from_text(text: str) -> list[float]:
    values = json.loads(text)
    if not isinstance(values, list):
        raise ValueError("Not a vector literal")
    return [float(x) for x in values]

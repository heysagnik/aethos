"""A vector column: pgvector on PostgreSQL, JSON text elsewhere (tests, local SQLite)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from django.conf import settings
from django.db import models
from django.db.backends.base.base import BaseDatabaseWrapper

from core import vectors


class EmbeddingField(models.Field):
    description = "Embedding vector"

    def db_type(self, connection: BaseDatabaseWrapper) -> str:
        if connection.vendor == "postgresql":
            return f"vector({settings.EMBEDDING_DIM})"
        return "text"

    def get_prep_value(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return vectors.to_text(list(value))

    def from_db_value(
        self, value: Any, expression: Any, connection: BaseDatabaseWrapper
    ) -> list[float] | None:
        if value is None:
            return None
        if isinstance(value, str):
            return vectors.from_text(value)
        return [float(x) for x in value]

    def deconstruct(self) -> tuple[str, str, Sequence[Any], dict[str, Any]]:
        name, _path, args, kwargs = super().deconstruct()
        return name, "apps.indexing.fields.EmbeddingField", args, kwargs

"""Embedding bookkeeping. Vectors are computed by the indexer (BGE) and stored with each chunk."""

from __future__ import annotations

from django.db.models import Count

from apps.indexing.models import Chunk


def embedding_progress(repo_id: int) -> tuple[int, int]:
    """(chunks with an embedding, all chunks) for a repository."""
    counts = Chunk.objects.filter(file__repository_id=repo_id).aggregate(
        total=Count("id"), done=Count("embedding")
    )
    return counts["done"] or 0, counts["total"] or 0

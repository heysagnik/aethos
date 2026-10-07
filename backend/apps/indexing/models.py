from __future__ import annotations

from django.db import models

from apps.indexing.fields import EmbeddingField
from apps.repos.models import Repository


class IndexedFile(models.Model):
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name="files")
    path = models.CharField(max_length=1024)
    language = models.CharField(max_length=32, blank=True)
    content_hash = models.CharField(max_length=64)
    loc = models.IntegerField(default=0)
    is_test = models.BooleanField(default=False)
    indexed_sha = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["repository", "path"], name="uniq_file_per_repo")
        ]

    def __str__(self) -> str:
        return self.path


class Symbol(models.Model):
    file = models.ForeignKey(IndexedFile, on_delete=models.CASCADE, related_name="symbols")
    name = models.CharField(max_length=255)
    qualified_name = models.CharField(max_length=512)
    kind = models.CharField(max_length=32)
    start_line = models.IntegerField()
    end_line = models.IntegerField()
    signature = models.TextField(blank=True)
    exported = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["file", "qualified_name"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self) -> str:
        return self.qualified_name


class EdgeKind(models.TextChoices):
    IMPORTS = "imports", "Imports"
    CALLS = "calls", "Calls"
    TESTS = "tests", "Tests"


class Edge(models.Model):
    """Directed dependency. `from_symbol`/`to_symbol` are null for file-level edges."""

    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name="edges")
    kind = models.CharField(max_length=16, choices=EdgeKind.choices)
    from_file = models.ForeignKey(
        IndexedFile, on_delete=models.CASCADE, related_name="outgoing_edges"
    )
    to_file = models.ForeignKey(
        IndexedFile, on_delete=models.CASCADE, related_name="incoming_edges"
    )
    from_symbol = models.ForeignKey(
        Symbol, null=True, blank=True, on_delete=models.CASCADE, related_name="outgoing_edges"
    )
    to_symbol = models.ForeignKey(
        Symbol, null=True, blank=True, on_delete=models.CASCADE, related_name="incoming_edges"
    )
    confidence = models.FloatField(default=1.0)

    class Meta:
        indexes = [
            models.Index(fields=["repository", "kind", "to_symbol"]),
            models.Index(fields=["repository", "kind", "from_symbol"]),
            models.Index(fields=["repository", "kind", "to_file"]),
            models.Index(fields=["repository", "kind", "from_file"]),
        ]


class Chunk(models.Model):
    """Searchable text of one symbol (or one file when it has no symbols)."""

    symbol = models.ForeignKey(
        Symbol, null=True, blank=True, on_delete=models.CASCADE, related_name="chunks"
    )
    file = models.ForeignKey(IndexedFile, on_delete=models.CASCADE, related_name="chunks")
    part = models.IntegerField(default=0)
    text = models.TextField()
    token_count = models.IntegerField()
    # Space-delimited identifier tokens with a leading and trailing space, for lexical search.
    search_tokens = models.TextField(default=" ")
    # Filled asynchronously by the "embed" step; null until then.
    embedding = EmbeddingField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["file"])]

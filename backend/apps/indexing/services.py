"""Index ingestion. All writes for one batch happen in a single transaction."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.indexing.models import Chunk, Edge, IndexedFile, Symbol
from apps.repos.models import IndexStatus, Repository


@dataclass(frozen=True)
class SymbolIn:
    name: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int
    signature: str
    exported: bool


@dataclass(frozen=True)
class ChunkIn:
    symbol_index: int | None
    part: int
    text: str
    token_count: int
    search_tokens: str
    embedding: list[float] | None = None


@dataclass(frozen=True)
class FileIn:
    path: str
    language: str
    content_hash: str
    loc: int
    is_test: bool
    symbols: list[SymbolIn]
    chunks: list[ChunkIn]


@dataclass(frozen=True)
class EdgeIn:
    kind: str
    from_path: str
    from_symbol: str | None
    to_path: str
    to_symbol: str | None
    confidence: float


@transaction.atomic
def begin_index(repo: Repository, sha: str, current: dict[str, str]) -> tuple[list[str], int]:
    """Compare the repository's file hashes with the stored ones.

    Returns (paths that need uploading, number of stored files that no longer exist).
    """
    stored = dict(IndexedFile.objects.filter(repository=repo).values_list("path", "content_hash"))
    changed = sorted(p for p, h in current.items() if stored.get(p) != h)
    gone = [p for p in stored if p not in current]
    if gone:
        IndexedFile.objects.filter(repository=repo, path__in=gone).delete()
    repo.index_status = IndexStatus.INDEXING
    repo.save(update_fields=["index_status"])
    return changed, len(gone)


@transaction.atomic
def ingest_files(repo: Repository, sha: str, files: list[FileIn]) -> int:
    for item in files:
        record, _ = IndexedFile.objects.update_or_create(
            repository=repo,
            path=item.path,
            defaults={
                "language": item.language,
                "content_hash": item.content_hash,
                "loc": item.loc,
                "is_test": item.is_test,
                "indexed_sha": sha,
            },
        )
        record.symbols.all().delete()
        record.chunks.all().delete()
        symbols = Symbol.objects.bulk_create(
            [
                Symbol(
                    file=record,
                    name=s.name[:255],
                    qualified_name=s.qualified_name[:512],
                    kind=s.kind[:32],
                    start_line=s.start_line,
                    end_line=s.end_line,
                    signature=s.signature,
                    exported=s.exported,
                )
                for s in item.symbols
            ]
        )
        Chunk.objects.bulk_create(
            [
                Chunk(
                    file=record,
                    symbol=symbols[c.symbol_index] if c.symbol_index is not None else None,
                    part=c.part,
                    text=c.text,
                    token_count=c.token_count,
                    search_tokens=c.search_tokens,
                    # A vector of the wrong size (another model) is dropped, not stored.
                    embedding=c.embedding
                    if c.embedding and len(c.embedding) == settings.EMBEDDING_DIM
                    else None,
                )
                for c in item.chunks
                if c.symbol_index is None or 0 <= c.symbol_index < len(symbols)
            ]
        )
    return len(files)


@transaction.atomic
def ingest_edges(repo: Repository, edges: list[EdgeIn], *, first: bool) -> tuple[int, int]:
    """Store edges, resolving (path, qualified name) references. Returns (stored, skipped)."""
    if first:
        Edge.objects.filter(repository=repo).delete()
    paths = {e.from_path for e in edges} | {e.to_path for e in edges}
    files = {f.path: f for f in IndexedFile.objects.filter(repository=repo, path__in=paths)}
    wanted = {
        (files[p].pk, name)
        for e in edges
        for p, name in ((e.from_path, e.from_symbol), (e.to_path, e.to_symbol))
        if name and p in files
    }
    symbols: dict[tuple[int, str], Symbol] = {}
    if wanted:
        file_ids = {fid for fid, _ in wanted}
        for symbol in Symbol.objects.filter(file_id__in=file_ids).order_by("start_line"):
            symbols.setdefault((symbol.file_id, symbol.qualified_name), symbol)

    rows: list[Edge] = []
    skipped = 0
    for e in edges:
        source, target = files.get(e.from_path), files.get(e.to_path)
        if source is None or target is None:
            skipped += 1
            continue
        from_symbol = symbols.get((source.pk, e.from_symbol)) if e.from_symbol else None
        to_symbol = symbols.get((target.pk, e.to_symbol)) if e.to_symbol else None
        if (e.from_symbol and from_symbol is None) or (e.to_symbol and to_symbol is None):
            skipped += 1
            continue
        rows.append(
            Edge(
                repository=repo,
                kind=e.kind,
                from_file=source,
                to_file=target,
                from_symbol=from_symbol,
                to_symbol=to_symbol,
                confidence=e.confidence,
            )
        )
    Edge.objects.bulk_create(rows)
    return len(rows), skipped


@transaction.atomic
def finalize_index(repo: Repository, sha: str) -> dict[str, int | str]:
    repo.index_status = IndexStatus.READY
    repo.indexed_sha = sha
    repo.last_indexed_at = timezone.now()
    repo.file_count = IndexedFile.objects.filter(repository=repo).count()
    repo.symbol_count = Symbol.objects.filter(file__repository=repo).count()
    repo.edge_count = Edge.objects.filter(repository=repo).count()
    repo.save()
    return {
        "status": repo.index_status,
        "indexed_sha": sha,
        "files": repo.file_count,
        "symbols": repo.symbol_count,
        "edges": repo.edge_count,
    }


def mark_failed(repo: Repository) -> None:
    repo.index_status = IndexStatus.FAILED
    repo.save(update_fields=["index_status"])

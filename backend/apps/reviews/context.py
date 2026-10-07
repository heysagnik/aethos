"""Builds context-pack candidates from the code index (database reads only, no LLM)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.db import connection
from django.db.models import Count, FloatField, Q
from django.db.models.expressions import RawSQL

from apps.github.client import GitHubGateway
from apps.indexing.models import Chunk, Edge, EdgeKind, IndexedFile, Symbol
from apps.repos.models import IndexStatus, Repository
from core import vectors
from core.diff import FileDiff
from core.lexical import identifier_tokens, similarity
from core.pack import PackItem, SymbolRef, symbols_overlapping
from core.paths import is_code, is_test_path

logger = logging.getLogger(__name__)

MAX_SYMBOLS_PER_FILE = 6
MAX_EMBED_QUERIES = 6
MAX_PYTHON_SCAN = 3000
MAX_RELATED = 8
MAX_SIMILAR = 5
SIMILAR_MIN_SCORE = 0.25
SHORT_BODY_LINES = 40
MAX_BODY_LINES = 80
BASELINE_MAX_FILE_CHARS = 60_000
BASELINE_MAX_IMPORTED = 20


@dataclass
class Candidates:
    items: list[PackItem] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def add(self, section: str, title: str, text: str, reason: str, score: float = 0.0) -> None:
        self.items.append(PackItem(section, title, text, reason, score, order=len(self.items)))


def _ranges(lines: frozenset[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for line in sorted(lines):
        if out and line == out[-1][1] + 1:
            out[-1][1] = line
        else:
            out.append([line, line])
    return out


def _clip(text: str, max_lines: int) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"


def _chunk_text(symbol: Symbol) -> str:
    parts = sorted(symbol.chunks.all(), key=lambda c: c.part)
    return "\n".join(c.text for c in parts)


def _file_importance(path: str) -> float:
    if is_test_path(path):
        return 0.7
    return 1.0 if is_code(path) else 0.8


def _add_base(
    cands: Candidates, files: list[FileDiff], title: str, body: str, author: str, instructions: str
) -> None:
    meta_lines = [f"Title: {title}", f"Author: {author}"]
    if instructions.strip():
        meta_lines.append(f"Requested focus: {instructions.strip()}")
    if body.strip():
        meta_lines.append(f"Description:\n{body.strip()[:2000]}")
    cands.add("meta", "Pull request", "\n".join(meta_lines), "PR metadata")
    for file in files:
        for number, hunk in enumerate(file.hunks, start=1):
            text = f"File: {file.path} ({file.status})\n{hunk.render()}"
            cands.add(
                "diff",
                f"{file.path} hunk {number}",
                text,
                "changed code",
                score=_file_importance(file.path),
            )


def _indexed_files(repo: Repository, files: list[FileDiff]) -> dict[str, IndexedFile]:
    wanted = {f.old_path or f.path for f in files} | {f.path for f in files}
    return {f.path: f for f in IndexedFile.objects.filter(repository=repo, path__in=wanted)}


def _add_symbols(
    cands: Candidates, indexed: dict[str, IndexedFile], files: list[FileDiff]
) -> list[Symbol]:
    touched: list[Symbol] = []
    for file in files:
        record = indexed.get(file.old_path or file.path) or indexed.get(file.path)
        if record is None or not file.hunks:
            continue
        symbols = list(record.symbols.prefetch_related("chunks"))
        refs = [
            SymbolRef(s.name, s.qualified_name, s.kind, s.start_line, s.end_line) for s in symbols
        ]
        by_key = {(s.qualified_name, s.start_line): s for s in symbols}
        ranges = [h.old_range for h in file.hunks if h.old_count > 0 or h.old_start > 0]
        for ref in symbols_overlapping(ranges, refs)[:MAX_SYMBOLS_PER_FILE]:
            symbol = by_key[(ref.qualified_name, ref.start_line)]
            touched.append(symbol)
            body = _clip(_chunk_text(symbol), MAX_BODY_LINES)
            cands.add(
                "symbols",
                f"{record.path}: {symbol.qualified_name} "
                f"(lines {symbol.start_line}-{symbol.end_line})",
                body,
                "contains changed lines",
                score=1.0,
            )
    return touched


def _symbol_summary(symbol: Symbol) -> str:
    span = symbol.end_line - symbol.start_line + 1
    if span <= SHORT_BODY_LINES:
        body = _chunk_text(symbol)
        if body:
            return body
    return f"{symbol.signature or symbol.qualified_name}  # {symbol.file.path}:{symbol.start_line}"


def _add_related(cands: Candidates, repo: Repository, touched: list[Symbol]) -> None:
    ids = [s.pk for s in touched]
    if not ids:
        return
    callers = (
        Edge.objects.filter(repository=repo, kind=EdgeKind.CALLS, to_symbol_id__in=ids)
        .exclude(from_symbol_id__in=ids)
        .select_related("from_symbol__file")
        .prefetch_related("from_symbol__chunks")
        .order_by("-confidence", "id")
    )
    seen: set[int] = set()
    for edge in callers:
        symbol = edge.from_symbol
        if symbol is None or symbol.pk in seen or len(seen) >= MAX_RELATED:
            continue
        seen.add(symbol.pk)
        cands.add(
            "related",
            f"Caller {symbol.file.path}: {symbol.qualified_name}",
            _symbol_summary(symbol),
            "calls changed code",
            score=edge.confidence,
        )
    callees = (
        Edge.objects.filter(repository=repo, kind=EdgeKind.CALLS, from_symbol_id__in=ids)
        .exclude(to_symbol_id__in=ids)
        .select_related("to_symbol__file")
        .prefetch_related("to_symbol__chunks")
        .order_by("-confidence", "id")
    )
    seen_callees: set[int] = set()
    for edge in callees:
        symbol = edge.to_symbol
        if symbol is None or symbol.pk in seen_callees or len(seen_callees) >= MAX_RELATED:
            continue
        seen_callees.add(symbol.pk)
        cands.add(
            "related",
            f"Callee {symbol.file.path}: {symbol.qualified_name}",
            _symbol_summary(symbol),
            "called by changed code",
            score=edge.confidence * 0.9,
        )


def _fan_in(repo: Repository, touched: list[Symbol], threshold: int) -> list[str]:
    ids = [s.pk for s in touched]
    if not ids:
        return []
    rows = (
        Symbol.objects.filter(pk__in=ids)
        .annotate(
            fan_in=Count(
                "incoming_edges",
                filter=Q(incoming_edges__kind=EdgeKind.CALLS, incoming_edges__repository=repo),
                distinct=True,
            )
        )
        .filter(fan_in__gte=threshold)
        .select_related("file")
        .order_by("-fan_in", "qualified_name")
    )
    return [f"{s.qualified_name} in {s.file.path} ({s.fan_in} dependents)" for s in rows]


def _add_tests(
    cands: Candidates, repo: Repository, indexed: dict[str, IndexedFile], files: list[FileDiff]
) -> None:
    file_ids = [indexed[f.path].pk for f in files if f.path in indexed]
    if not file_ids:
        return
    edges = (
        Edge.objects.filter(repository=repo, kind=EdgeKind.TESTS, to_file_id__in=file_ids)
        .select_related("from_file")
        .order_by("from_file__path")
    )
    seen: set[int] = set()
    for edge in edges:
        test_file = edge.from_file
        if test_file.pk in seen or len(seen) >= 5:
            continue
        seen.add(test_file.pk)
        names = list(test_file.symbols.order_by("start_line").values_list("name", flat=True)[:30])
        cands.add(
            "tests",
            f"Tests {test_file.path}",
            f"{test_file.path}\n" + "\n".join(f"- {n}" for n in names),
            "tests the changed file",
            score=1.0,
        )


def _added_text(files: list[FileDiff]) -> str:
    return "\n".join(
        line.text for f in files for h in f.hunks for line in h.lines if line.kind == "add"
    )


def _similar_by_embedding(
    repo: Repository, indexed: dict[str, IndexedFile], touched: list[Symbol]
) -> list[tuple[float, Chunk]] | None:
    """Nearest chunks to the code being changed, or None if no stored vectors can be used.

    The query vectors are the stored embeddings of the changed symbols (as of the indexed base
    branch), so no embedding service is called at review time.
    """
    queries = [
        chunk.embedding
        for chunk in Chunk.objects.filter(
            symbol_id__in=[s.pk for s in touched[:MAX_EMBED_QUERIES]], embedding__isnull=False
        ).order_by("symbol_id", "part")[:MAX_EMBED_QUERIES]
        if chunk.embedding
    ]
    if not queries:
        return None
    pool = (
        Chunk.objects.filter(file__repository=repo, embedding__isnull=False)
        .exclude(file_id__in=[r.pk for r in indexed.values()])
        .select_related("file", "symbol")
    )
    best: dict[int, tuple[float, Chunk]] = {}
    if connection.vendor == "postgresql":
        for query in queries:
            ranked = pool.annotate(
                distance=RawSQL(
                    '"indexing_chunk"."embedding" <=> %s::vector',
                    [vectors.to_text(query)],
                    output_field=FloatField(),
                )
            ).order_by("distance")[: MAX_SIMILAR * 2]
            for ranked_chunk in ranked:
                score = 1.0 - float(getattr(ranked_chunk, "distance"))  # noqa: B009
                if score > best.get(ranked_chunk.pk, (-1.0, ranked_chunk))[0]:
                    best[ranked_chunk.pk] = (score, ranked_chunk)
    else:
        candidates = list(pool[:MAX_PYTHON_SCAN])
        for query in queries:
            for chunk in candidates:
                score = vectors.cosine(query, chunk.embedding or [])
                if score > best.get(chunk.pk, (-1.0, chunk))[0]:
                    best[chunk.pk] = (score, chunk)
    scored = [pair for pair in best.values() if pair[0] >= settings.EMBED_MIN_SIMILARITY]
    scored.sort(key=lambda pair: (-pair[0], pair[1].pk))
    return scored[:MAX_SIMILAR]


def _similar_by_tokens(
    repo: Repository, indexed: dict[str, IndexedFile], files: list[FileDiff]
) -> list[tuple[float, Chunk]]:
    query = identifier_tokens(_added_text(files))
    if len(query) < 3:
        return []
    probe = sorted(query, key=lambda t: (-len(t), t))[:8]
    condition = Q()
    for token in probe:
        condition |= Q(search_tokens__contains=f" {token} ")
    pool = (
        Chunk.objects.filter(file__repository=repo)
        .filter(condition)
        .exclude(file_id__in=[r.pk for r in indexed.values()])
        .select_related("file", "symbol")[:300]
    )
    scored = [(similarity(query, set(chunk.search_tokens.split())), chunk) for chunk in pool]
    scored = [pair for pair in scored if pair[0] >= SIMILAR_MIN_SCORE]
    scored.sort(key=lambda pair: (-pair[0], pair[1].pk))
    return scored[:MAX_SIMILAR]


def _add_similar(
    cands: Candidates,
    repo: Repository,
    indexed: dict[str, IndexedFile],
    files: list[FileDiff],
    touched: list[Symbol],
) -> None:
    scored = _similar_by_embedding(repo, indexed, touched)
    method = "embedding"
    if scored is None:
        method = "lexical"
        scored = _similar_by_tokens(repo, indexed, files)
    cands.meta["similar_method"] = method
    for score, chunk in scored:
        name = chunk.symbol.qualified_name if chunk.symbol else chunk.file.path
        cands.add(
            "similar",
            f"{chunk.file.path}: {name}",
            _clip(chunk.text, 60),
            f"similar to the change by {method} (score {score:.2f})",
            score=score,
        )


def _add_repo_map(cands: Candidates, repo: Repository) -> None:
    rows = (
        IndexedFile.objects.filter(repository=repo)
        .annotate(degree=Count("incoming_edges", filter=Q(incoming_edges__kind=EdgeKind.IMPORTS)))
        .filter(degree__gt=0)
        .order_by("-degree", "path")[:15]
    )
    lines = []
    for record in rows:
        names = list(
            record.symbols.filter(exported=True)
            .order_by("start_line")
            .values_list("name", flat=True)[:5]
        )
        suffix = f": {', '.join(names)}" if names else ""
        lines.append(f"{record.path} (imported by {record.degree}){suffix}")
    if lines:
        cands.add("map", "Most depended-on files", "\n".join(lines), "repository orientation")


def build_aethos_candidates(
    *,
    repo: Repository,
    files: list[FileDiff],
    pr_title: str,
    pr_body: str,
    author: str,
    instructions: str,
    base_sha: str,
    fan_in_threshold: int,
) -> Candidates:
    cands = Candidates()
    _add_base(cands, files, pr_title, pr_body, author, instructions)
    index_ready = repo.index_status == IndexStatus.READY and bool(repo.indexed_sha)
    cands.meta.update(
        {
            "mode": "aethos",
            "index_used": index_ready,
            "index_sha": repo.indexed_sha,
            "index_stale": index_ready and repo.indexed_sha != base_sha,
        }
    )
    touched: list[Symbol] = []
    if index_ready:
        indexed = _indexed_files(repo, files)
        touched = _add_symbols(cands, indexed, files)
        _add_related(cands, repo, touched)
        _add_tests(cands, repo, indexed, files)
        _add_similar(cands, repo, indexed, files, touched)
        _add_repo_map(cands, repo)
    cands.meta["high_fan_in"] = _fan_in(repo, touched, fan_in_threshold) if touched else []
    return cands


def build_baseline_candidates(
    *,
    repo: Repository,
    files: list[FileDiff],
    pr_title: str,
    pr_body: str,
    author: str,
    instructions: str,
    head_sha: str,
    gateway: GitHubGateway,
) -> Candidates:
    """Naive comparison mode: changed files in full plus the files they import, unranked."""
    cands = Candidates()
    _add_base(cands, files, pr_title, pr_body, author, instructions)
    cands.meta.update({"mode": "baseline", "index_used": False, "high_fan_in": []})
    full_paths: set[str] = set()
    for file in files:
        text = gateway.get_file_text(repo.full_name, file.path, head_sha)
        if text is None:
            continue
        full_paths.add(file.path)
        cands.add(
            "symbols",
            f"Full file {file.path}",
            text[:BASELINE_MAX_FILE_CHARS],
            "baseline: whole changed file",
            score=1.0,
        )
    imported = (
        IndexedFile.objects.filter(
            repository=repo,
            incoming_edges__kind=EdgeKind.IMPORTS,
            incoming_edges__from_file__path__in=full_paths,
        )
        .exclude(path__in=full_paths)
        .distinct()
        .order_by("path")[:BASELINE_MAX_IMPORTED]
    )
    for record in imported:
        text = gateway.get_file_text(repo.full_name, record.path, head_sha)
        if text:
            cands.add(
                "related",
                f"Imported file {record.path}",
                text[:BASELINE_MAX_FILE_CHARS],
                "baseline: imported by a changed file",
                score=1.0,
            )
    return cands


def commentable_map(files: list[FileDiff]) -> dict[str, list[list[int]]]:
    return {f.path: _ranges(f.commentable_lines) for f in files}


def source_stats(files: list[FileDiff]) -> tuple[int, bool]:
    """(changed source lines excluding tests, whether any test file changed)."""
    source = sum(
        f.changed_line_count for f in files if is_code(f.path) and not is_test_path(f.path)
    )
    tests = any(is_test_path(f.path) for f in files)
    return source, tests

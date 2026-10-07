"""Server-side indexing: download the default branch, parse it, then embed the chunks.

Two queue steps keep every request short: "index" parses and stores the code (the repository is
usable for reviews as soon as it finishes), then "embed" fills in vectors a few batches at a time
and re-enqueues itself until every chunk has one.
"""

from __future__ import annotations

import io
import logging
import tarfile
from pathlib import PurePosixPath
from typing import Any

from django.conf import settings

from apps.github import client as github_client
from apps.indexing import nim, services
from apps.indexing.code.chunk import file_payload
from apps.indexing.code.graph import build_edges
from apps.indexing.code.parse import ParsedFile, language_for, parse_file
from apps.indexing.models import Chunk
from apps.repos.models import IndexStatus, Repository
from apps.reviews.queue import enqueue
from core.paths import DEFAULT_IGNORE_GLOBS, path_matches

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 300_000
FILE_BATCH = 100


def parse_archive(data: bytes) -> tuple[dict[str, ParsedFile], list[str]]:
    """Parse every supported source file in a GitHub tarball. Returns (files, failure notes)."""
    parsed: dict[str, ParsedFile] = {}
    failures: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive:
            if not member.isfile() or member.size > MAX_FILE_BYTES:
                continue
            # The first path segment is "<owner>-<repo>-<sha>/".
            parts = PurePosixPath(member.name).parts[1:]
            if not parts:
                continue
            path = "/".join(parts)
            if not language_for(path) or path_matches(path, DEFAULT_IGNORE_GLOBS):
                continue
            if len(parsed) >= settings.INDEX_MAX_FILES:
                failures.append(f"stopped after {settings.INDEX_MAX_FILES} files")
                break
            handle = archive.extractfile(member)
            if handle is None:
                continue
            try:
                result = parse_file(path, handle.read())
            except Exception as exc:  # one bad file must not fail the whole run
                failures.append(f"{path}: {type(exc).__name__}: {exc}")
                continue
            if result is not None:
                parsed[path] = result
    return parsed, failures


def _to_file_in(payload: dict[str, Any]) -> services.FileIn:
    return services.FileIn(
        path=payload["path"],
        language=payload["language"],
        content_hash=payload["content_hash"],
        loc=payload["loc"],
        is_test=payload["is_test"],
        symbols=[services.SymbolIn(**s) for s in payload["symbols"]],
        chunks=[services.ChunkIn(**{**c, "embedding": None}) for c in payload["chunks"]],
    )


def step_index(payload: dict[str, Any]) -> None:
    repo = Repository.objects.select_related("installation").get(pk=payload["repo_id"])
    if repo.removed_at is not None or repo.installation.suspended_at is not None:
        return
    gateway = github_client.get_gateway(repo.installation.github_installation_id)
    sha = gateway.get_branch_sha(repo.full_name, repo.default_branch)
    archive = gateway.download_archive(repo.full_name, sha, settings.INDEX_MAX_ARCHIVE_BYTES)
    parsed, failures = parse_archive(archive)
    for failure in failures[:20]:
        logger.warning("Index %s skipped %s", repo.full_name, failure)

    changed, _ = services.begin_index(repo, sha, {p: f.content_hash for p, f in parsed.items()})
    wanted = [p for p in changed if p in parsed]
    for start in range(0, len(wanted), FILE_BATCH):
        batch = [_to_file_in(file_payload(parsed[p])) for p in wanted[start : start + FILE_BATCH]]
        services.ingest_files(repo, sha, batch)
    edges = [
        services.EdgeIn(e.kind, e.from_path, e.from_symbol, e.to_path, e.to_symbol, e.confidence)
        for e in build_edges(parsed)
    ]
    services.ingest_edges(repo, edges, first=True)
    services.finalize_index(repo, sha)
    if nim.is_configured():
        enqueue("embed", {"repo_id": repo.pk}, f"embed-{repo.pk}-{sha}")


def step_embed(payload: dict[str, Any]) -> None:
    repo = Repository.objects.get(pk=payload["repo_id"])
    pending = Chunk.objects.filter(file__repository=repo, embedding__isnull=True).select_related(
        "file", "symbol"
    )
    size = settings.EMBED_BATCH_SIZE
    for _ in range(settings.EMBED_BATCHES_PER_STEP):
        batch = list(pending.order_by("pk")[:size])
        if not batch:
            return
        texts = [
            nim.chunk_embedding_text(
                c.file.path, c.symbol.qualified_name if c.symbol else "", c.text
            )
            for c in batch
        ]
        for chunk, vec in zip(batch, nim.embed_texts(texts, "passage"), strict=True):
            chunk.embedding = vec
        Chunk.objects.bulk_update(batch, ["embedding"])
    remaining = pending.count()
    if remaining:
        enqueue("embed", {"repo_id": repo.pk}, f"embed-{repo.pk}-{remaining}")


def mark_failed(repo_id: int) -> None:
    repo = Repository.objects.filter(pk=repo_id).first()
    if repo is not None and repo.index_status != IndexStatus.READY:
        services.mark_failed(repo)

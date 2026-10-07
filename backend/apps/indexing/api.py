from __future__ import annotations

from typing import Literal

from django.http import HttpRequest
from ninja import NinjaAPI, Schema
from pydantic import Field

from apps.indexing import services
from apps.indexing.auth import OidcBearer
from apps.repos.models import Repository

api = NinjaAPI(urls_namespace="index", docs_url=None, openapi_url=None, auth=OidcBearer())

MAX_FILES_PER_BATCH = 200
MAX_EDGES_PER_BATCH = 5000
SHA = Field(min_length=7, max_length=64)


def _repo(request: HttpRequest) -> Repository:
    repo: Repository = request.indexed_repo  # type: ignore[attr-defined]
    return repo


class FileHash(Schema):
    path: str = Field(max_length=1024)
    hash: str = Field(min_length=8, max_length=64)


class BeginIn(Schema):
    sha: str = SHA
    files: list[FileHash] = Field(max_length=100_000)


class BeginOut(Schema):
    changed: list[str]
    deleted: int


class SymbolSchema(Schema):
    name: str = Field(max_length=255)
    qualified_name: str = Field(max_length=512)
    kind: str = Field(max_length=32)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    signature: str = Field(default="", max_length=2000)
    exported: bool = False


class ChunkSchema(Schema):
    symbol_index: int | None = None
    part: int = Field(default=0, ge=0)
    text: str = Field(max_length=60_000)
    token_count: int = Field(ge=0)
    search_tokens: str = Field(default=" ", max_length=4000)
    embedding: list[float] | None = Field(default=None, max_length=4096)


class FileSchema(Schema):
    path: str = Field(max_length=1024)
    language: str = Field(default="", max_length=32)
    content_hash: str = Field(min_length=8, max_length=64)
    loc: int = Field(default=0, ge=0)
    is_test: bool = False
    symbols: list[SymbolSchema] = Field(default_factory=list, max_length=5000)
    chunks: list[ChunkSchema] = Field(default_factory=list, max_length=10_000)


class FilesIn(Schema):
    sha: str = SHA
    files: list[FileSchema] = Field(max_length=MAX_FILES_PER_BATCH)


class EdgeSchema(Schema):
    kind: Literal["imports", "calls", "tests"]
    from_path: str = Field(max_length=1024)
    from_symbol: str | None = Field(default=None, max_length=512)
    to_path: str = Field(max_length=1024)
    to_symbol: str | None = Field(default=None, max_length=512)
    confidence: float = Field(default=1.0, ge=0, le=1)


class EdgesIn(Schema):
    first: bool = False
    edges: list[EdgeSchema] = Field(max_length=MAX_EDGES_PER_BATCH)


class FinalizeIn(Schema):
    sha: str = SHA


class StateOut(Schema):
    status: str
    indexed_sha: str


@api.get("/state", response=StateOut, url_name="state")
def state(request: HttpRequest) -> StateOut:
    repo = _repo(request)
    return StateOut(status=repo.index_status, indexed_sha=repo.indexed_sha)


@api.post("/begin", response=BeginOut, url_name="begin")
def begin(request: HttpRequest, body: BeginIn) -> BeginOut:
    current = {f.path: f.hash for f in body.files}
    changed, deleted = services.begin_index(_repo(request), body.sha, current)
    return BeginOut(changed=changed, deleted=deleted)


@api.post("/files", url_name="files")
def files(request: HttpRequest, body: FilesIn) -> dict[str, int]:
    items = [
        services.FileIn(
            path=f.path,
            language=f.language,
            content_hash=f.content_hash,
            loc=f.loc,
            is_test=f.is_test,
            symbols=[services.SymbolIn(**s.model_dump()) for s in f.symbols],
            chunks=[services.ChunkIn(**c.model_dump()) for c in f.chunks],
        )
        for f in body.files
    ]
    return {"stored": services.ingest_files(_repo(request), body.sha, items)}


@api.post("/edges", url_name="edges")
def edges(request: HttpRequest, body: EdgesIn) -> dict[str, int]:
    items = [services.EdgeIn(**e.model_dump()) for e in body.edges]
    stored, skipped = services.ingest_edges(_repo(request), items, first=body.first)
    return {"stored": stored, "skipped": skipped}


@api.post("/finalize", url_name="finalize")
def finalize(request: HttpRequest, body: FinalizeIn) -> dict[str, int | str]:
    return services.finalize_index(_repo(request), body.sha)


@api.post("/fail", url_name="fail")
def fail(request: HttpRequest) -> dict[str, bool]:
    services.mark_failed(_repo(request))
    return {"ok": True}

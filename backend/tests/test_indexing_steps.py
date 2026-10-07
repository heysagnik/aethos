from __future__ import annotations

import io
import tarfile
from dataclasses import dataclass

import httpx
import pytest
import respx

from apps.github import client as github_client
from apps.github.handlers import handle_event
from apps.indexing import indexer, nim
from apps.indexing.models import Chunk, Edge, IndexedFile, Symbol
from apps.repos.models import IndexStatus

DIM = 2048

UTILS = b"def helper(x):\n    return x * 2\n"
MAIN = b"from app.utils import helper\n\n\ndef main():\n    return helper(1)\n"


def make_archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path, content in files.items():
            info = tarfile.TarInfo(f"acme-app-abc123/{path}")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


@dataclass
class ArchiveGateway:
    archive: bytes
    sha: str = "a" * 40

    def get_branch_sha(self, repo: str, branch: str) -> str:
        return self.sha

    def download_archive(self, repo: str, ref: str, max_bytes: int) -> bytes:
        return self.archive


@pytest.fixture
def gateway(monkeypatch):
    gw = ArchiveGateway(
        make_archive({"app/utils.py": UTILS, "app/main.py": MAIN, "README.md": b"x"})
    )
    monkeypatch.setattr(github_client, "get_gateway", lambda _id: gw)
    return gw


def fake_embed(texts, input_type="passage", *, client=None):
    return [[1.0] + [0.0] * (DIM - 1) for _ in texts]


def test_index_step_parses_the_repository(db, repo, gateway, monkeypatch):
    monkeypatch.setattr(nim, "embed_texts", fake_embed)
    indexer.step_index({"repo_id": repo.pk})
    repo.refresh_from_db()
    assert repo.index_status == IndexStatus.READY and repo.indexed_sha == "a" * 40
    assert set(IndexedFile.objects.values_list("path", flat=True)) == {
        "app/utils.py",
        "app/main.py",
    }
    assert Symbol.objects.filter(qualified_name="helper").exists()
    assert Edge.objects.filter(repository=repo, kind="calls").exists()
    # QUEUE_MODE is inline in tests, so the embed step already ran.
    assert Chunk.objects.filter(embedding__isnull=True).count() == 0
    assert Chunk.objects.first().embedding[0] == 1.0


def test_reindex_only_replaces_changed_files(db, repo, gateway, monkeypatch):
    monkeypatch.setattr(nim, "embed_texts", fake_embed)
    indexer.step_index({"repo_id": repo.pk})
    untouched = IndexedFile.objects.get(path="app/main.py").pk
    gateway.archive = make_archive({"app/utils.py": UTILS + b"\n# edit\n", "app/main.py": MAIN})
    indexer.step_index({"repo_id": repo.pk})
    assert IndexedFile.objects.get(path="app/main.py").pk == untouched
    gateway.archive = make_archive({"app/main.py": MAIN})
    indexer.step_index({"repo_id": repo.pk})
    assert list(IndexedFile.objects.values_list("path", flat=True)) == ["app/main.py"]


def test_index_without_an_api_key_skips_embedding(db, repo, gateway, settings):
    settings.NVIDIA_API_KEY = ""
    indexer.step_index({"repo_id": repo.pk})
    repo.refresh_from_db()
    assert repo.index_status == IndexStatus.READY
    assert Chunk.objects.exists() and Chunk.objects.filter(embedding__isnull=False).count() == 0


def test_embed_step_continues_until_done(db, repo, gateway, settings, monkeypatch):
    settings.EMBED_BATCH_SIZE = 1
    settings.EMBED_BATCHES_PER_STEP = 1
    monkeypatch.setattr(nim, "embed_texts", fake_embed)
    indexer.step_index({"repo_id": repo.pk})
    assert Chunk.objects.count() >= 2
    assert Chunk.objects.filter(embedding__isnull=True).count() == 0


def test_failed_step_marks_the_index_failed(db, repo):
    from apps.reviews import pipeline

    pipeline.mark_failed("index", {"repo_id": repo.pk}, "boom")
    repo.refresh_from_db()
    assert repo.index_status == IndexStatus.FAILED


def test_push_to_default_branch_queues_an_index(db, repo, gateway, monkeypatch):
    monkeypatch.setattr(nim, "embed_texts", fake_embed)
    payload = {
        "ref": f"refs/heads/{repo.default_branch}",
        "repository": {"id": repo.github_repo_id},
    }
    assert handle_event("push", payload) == "index queued"
    repo.refresh_from_db()
    assert repo.index_status == IndexStatus.READY
    other = {**payload, "ref": "refs/heads/feature"}
    assert handle_event("push", other) == "ignored: not the default branch"
    assert handle_event("push", {"ref": "x", "repository": {"id": 1}}) == (
        "ignored: unknown repository"
    )


def test_reindex_endpoint(db, client, user, repo, gateway, monkeypatch):
    monkeypatch.setattr(nim, "embed_texts", fake_embed)
    client.force_login(user)
    response = client.post(f"/api/dashboard/repos/{repo.pk}/index")
    assert response.status_code == 200
    assert response.json()["index_status"] == "ready" and response.json()["file_count"] == 2


@respx.mock
def test_nim_client_request_and_response(settings):
    route = respx.post(f"{settings.NVIDIA_BASE_URL}/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 3.0] + [0.0] * (DIM - 2)},
                    {"index": 0, "embedding": [4.0, 0.0] + [0.0] * (DIM - 2)},
                ]
            },
        )
    )
    out = nim.embed_texts(["a", "b"], "query")
    assert out[0][:2] == [1.0, 0.0] and out[1][:2] == [0.0, 1.0]
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer test-key"
    body = request.read().decode()
    assert '"input_type":"query"' in body.replace(" ", "")
    assert "nvidia/nemotron-3-embed-1b" in body


@respx.mock
def test_nim_client_rejects_wrong_dimension_and_retries(settings, monkeypatch):
    monkeypatch.setattr(nim.time, "sleep", lambda _s: None)
    url = f"{settings.NVIDIA_BASE_URL}/embeddings"
    respx.post(url).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 2.0]}]}),
        ]
    )
    with pytest.raises(nim.EmbeddingError, match="dimensions"):
        nim.embed_texts(["a"])


@respx.mock
def test_nim_client_gives_up_on_client_errors(settings):
    respx.post(f"{settings.NVIDIA_BASE_URL}/embeddings").mock(return_value=httpx.Response(401))
    with pytest.raises(nim.EmbeddingError, match="401"):
        nim.embed_texts(["a"])

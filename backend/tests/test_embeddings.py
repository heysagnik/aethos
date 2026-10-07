from __future__ import annotations

import math

import pytest

from apps.github import client as github_client
from apps.indexing import embeddings
from apps.indexing.models import Chunk, IndexedFile
from apps.reviews import llm
from apps.reviews.models import Review, ReviewStatus
from core import vectors
from tests.conftest import FakeGateway, FakeLLM, make_pull
from tests.test_pipeline import DIFF, REVIEW_JSON, _install_index

DIM = 2048


def unit(index: int) -> list[float]:
    vec = [0.0] * DIM
    vec[index] = 1.0
    return vec


def test_vector_helpers():
    assert vectors.normalize([3.0, 4.0]) == [0.6, 0.8]
    assert vectors.normalize([0.0, 0.0]) == [0.0, 0.0]
    assert vectors.cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert vectors.cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert vectors.cosine([1.0], [1.0, 2.0]) == 0.0
    assert vectors.from_text(vectors.to_text([0.5, -1.25, 3.0])) == [0.5, -1.25, 3.0]
    assert math.isclose(sum(x * x for x in vectors.normalize([1.0, 2.0, 3.0])), 1.0)


def test_embedding_field_round_trips(db, indexed_repo):
    record = IndexedFile.objects.create(repository=indexed_repo, path="a.py", content_hash="h" * 64)
    chunk = Chunk.objects.create(file=record, text="x", token_count=1, embedding=[0.25, -0.5])
    assert Chunk.objects.get(pk=chunk.pk).embedding == [0.25, -0.5]
    empty = Chunk.objects.create(file=record, text="y", token_count=1)
    assert Chunk.objects.get(pk=empty.pk).embedding is None
    assert Chunk.objects.filter(embedding__isnull=True).count() == 1


def _ingest(repo, embedding):
    from apps.indexing import services

    services.ingest_files(
        repo,
        "1" * 40,
        [
            services.FileIn(
                path="m.py",
                language="python",
                content_hash="h" * 64,
                loc=1,
                is_test=False,
                symbols=[],
                chunks=[services.ChunkIn(None, 0, "x", 1, " x ", embedding)],
            )
        ],
    )


def test_stored_embeddings_are_counted(db, repo):
    _ingest(repo, unit(3))
    assert Chunk.objects.get().embedding == unit(3)
    assert embeddings.embedding_progress(repo.pk) == (1, 1)


def test_wrong_size_or_missing_embeddings_are_dropped(db, repo):
    _ingest(repo, [1.0, 2.0])
    assert Chunk.objects.get().embedding is None
    _ingest(repo, None)
    assert Chunk.objects.get().embedding is None
    assert embeddings.embedding_progress(repo.pk) == (0, 1)


@pytest.fixture
def review_env(monkeypatch, indexed_repo):
    _install_index(indexed_repo)
    # helper() is the changed symbol; app/main.py is not in the diff and is its nearest neighbour.
    Chunk.objects.filter(file__path="app/utils.py").update(embedding=unit(0))
    Chunk.objects.filter(file__path="app/main.py").update(embedding=unit(0))
    gateway = FakeGateway(make_pull(), DIFF)
    monkeypatch.setattr(github_client, "get_gateway", lambda _id: gateway)
    monkeypatch.setattr(llm, "get_llm", lambda: FakeLLM([REVIEW_JSON]))
    return gateway


def test_review_searches_with_stored_vectors(review_env, indexed_repo):
    from apps.reviews import pipeline

    pipeline.run_step_chain("triage", {"repo_id": indexed_repo.pk, "pr_number": 7, "comment_id": 1})
    review = Review.objects.get()
    assert review.status == ReviewStatus.POSTED
    assert review.pack["meta"]["similar_method"] == "embedding"
    similar = [i for i in review.pack["items"] if i["section"] == "similar"]
    assert [i["title"].split(":")[0] for i in similar] == ["app/main.py"]
    assert "embedding" in similar[0]["reason"]
    assert not review.usage.exclude(step="review").exists()  # no embedding service is called


def test_review_falls_back_to_lexical_without_vectors(review_env, indexed_repo):
    from apps.reviews import pipeline

    Chunk.objects.update(embedding=None)
    pipeline.run_step_chain("triage", {"repo_id": indexed_repo.pk, "pr_number": 7, "comment_id": 1})
    review = Review.objects.get()
    assert review.status == ReviewStatus.POSTED
    assert review.pack["meta"]["similar_method"] == "lexical"

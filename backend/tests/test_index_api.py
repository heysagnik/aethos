from __future__ import annotations

import pytest

from apps.indexing import auth
from apps.indexing.models import Chunk, Edge, IndexedFile, Symbol
from apps.repos.models import IndexStatus

BASE = "/api/index"


@pytest.fixture
def authed(monkeypatch, repo):
    monkeypatch.setattr(
        auth,
        "verify_oidc_token",
        lambda token: auth.OidcClaims(
            repo.github_repo_id, repo.full_name, "refs/heads/main", "s" * 40
        ),
    )
    return {"HTTP_AUTHORIZATION": "Bearer good"}


def _file(path, qnames, h="a" * 64):
    return {
        "path": path,
        "language": "python",
        "content_hash": h,
        "loc": 10,
        "symbols": [
            {
                "name": q.split(".")[-1],
                "qualified_name": q,
                "kind": "function",
                "start_line": i * 3 + 1,
                "end_line": i * 3 + 3,
                "signature": f"def {q}()",
                "exported": True,
            }
            for i, q in enumerate(qnames)
        ],
        "chunks": [
            {
                "symbol_index": i,
                "part": 0,
                "text": f"def {q}(): pass",
                "token_count": 5,
                "search_tokens": f" {q} ",
            }
            for i, q in enumerate(qnames)
        ],
    }


def post(client, path, body, headers):
    return client.post(f"{BASE}{path}", data=body, content_type="application/json", **headers)


def test_requires_valid_token(client, repo, monkeypatch):
    assert client.get(f"{BASE}/state").status_code == 401

    def deny(token):
        raise auth.OidcError("bad")

    monkeypatch.setattr(auth, "verify_oidc_token", deny)
    assert client.get(f"{BASE}/state", HTTP_AUTHORIZATION="Bearer nope").status_code == 401


def test_only_default_branch_is_accepted(client, repo, monkeypatch):
    monkeypatch.setattr(
        auth,
        "verify_oidc_token",
        lambda token: auth.OidcClaims(
            repo.github_repo_id, repo.full_name, "refs/heads/feature", "s"
        ),
    )
    assert client.get(f"{BASE}/state", HTTP_AUTHORIZATION="Bearer t").status_code == 401


def test_full_index_then_incremental_update(client, repo, authed):
    sha1 = "1" * 40
    begin = post(
        client,
        "/begin",
        {
            "sha": sha1,
            "files": [{"path": "a.py", "hash": "a" * 64}, {"path": "b.py", "hash": "b" * 64}],
        },
        authed,
    )
    assert begin.json() == {"changed": ["a.py", "b.py"], "deleted": 0}
    repo.refresh_from_db()
    assert repo.index_status == IndexStatus.INDEXING

    post(
        client,
        "/files",
        {
            "sha": sha1,
            "files": [_file("a.py", ["foo", "Bar.baz"]), _file("b.py", ["qux"], "b" * 64)],
        },
        authed,
    )
    edges = post(
        client,
        "/edges",
        {
            "first": True,
            "edges": [
                {"kind": "imports", "from_path": "b.py", "to_path": "a.py"},
                {
                    "kind": "calls",
                    "from_path": "b.py",
                    "from_symbol": "qux",
                    "to_path": "a.py",
                    "to_symbol": "foo",
                    "confidence": 0.9,
                },
                {
                    "kind": "calls",
                    "from_path": "b.py",
                    "from_symbol": "missing",
                    "to_path": "a.py",
                    "to_symbol": "foo",
                },
                {"kind": "imports", "from_path": "ghost.py", "to_path": "a.py"},
            ],
        },
        authed,
    )
    assert edges.json() == {"stored": 2, "skipped": 2}
    done = post(client, "/finalize", {"sha": sha1}, authed).json()
    assert done == {"status": "ready", "indexed_sha": sha1, "files": 2, "symbols": 3, "edges": 2}
    assert Chunk.objects.filter(file__repository=repo).count() == 3

    # Second run: a.py unchanged, b.py changed, c.py new, nothing deleted.
    sha2 = "2" * 40
    plan = post(
        client,
        "/begin",
        {
            "sha": sha2,
            "files": [
                {"path": "a.py", "hash": "a" * 64},
                {"path": "b.py", "hash": "e" * 64},
                {"path": "c.py", "hash": "c" * 64},
            ],
        },
        authed,
    ).json()
    assert plan == {"changed": ["b.py", "c.py"], "deleted": 0}
    a_symbol_ids = set(Symbol.objects.filter(file__path="a.py").values_list("pk", flat=True))
    post(
        client,
        "/files",
        {
            "sha": sha2,
            "files": [_file("b.py", ["qux", "quux"], "e" * 64), _file("c.py", ["zed"], "c" * 64)],
        },
        authed,
    )
    assert (
        set(Symbol.objects.filter(file__path="a.py").values_list("pk", flat=True)) == a_symbol_ids
    )
    post(
        client,
        "/edges",
        {
            "first": True,
            "edges": [
                {
                    "kind": "calls",
                    "from_path": "c.py",
                    "from_symbol": "zed",
                    "to_path": "a.py",
                    "to_symbol": "foo",
                }
            ],
        },
        authed,
    )
    post(client, "/finalize", {"sha": sha2}, authed)
    assert Edge.objects.filter(repository=repo).count() == 1
    repo.refresh_from_db()
    assert repo.indexed_sha == sha2 and repo.symbol_count == 5

    # Third run: b.py and c.py disappear from the repository.
    plan = post(
        client, "/begin", {"sha": "3" * 40, "files": [{"path": "a.py", "hash": "a" * 64}]}, authed
    )
    assert plan.json() == {"changed": [], "deleted": 2}
    assert list(IndexedFile.objects.filter(repository=repo).values_list("path", flat=True)) == [
        "a.py"
    ]


def test_failure_marks_index_failed(client, repo, authed):
    assert post(client, "/fail", {}, authed).json() == {"ok": True}
    repo.refresh_from_db()
    assert repo.index_status == IndexStatus.FAILED


def test_rejects_oversized_batches(client, repo, authed):
    too_many = [_file(f"f{i}.py", []) for i in range(201)]
    assert post(client, "/files", {"sha": "1" * 40, "files": too_many}, authed).status_code == 422

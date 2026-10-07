from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from django.conf import settings
from django.test import Client

from apps.accounts.models import User
from apps.github.client import GitHubError, PullInfo
from apps.repos.models import IndexStatus, Installation, InstallationMember, Repository
from apps.reviews import llm


@dataclass
class FakeGateway:
    pull: PullInfo
    diff: str
    ci_state: str = "success"
    files: dict[str, str] = field(default_factory=dict)
    reject_inline: bool = False
    reviews: list[dict[str, Any]] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    reactions: list[str] = field(default_factory=list)

    def get_pull(self, repo: str, number: int) -> PullInfo:
        return self.pull

    def get_diff(self, repo: str, number: int) -> str:
        return self.diff

    def get_ci_state(self, repo: str, sha: str) -> str:
        return self.ci_state

    def get_file_text(self, repo: str, path: str, ref: str) -> str | None:
        return self.files.get(path)

    def create_review(
        self, repo: str, number: int, head_sha: str, body: str, comments: list[dict[str, Any]]
    ) -> int:
        if self.reject_inline and comments:
            raise GitHubError(422, "Line could not be resolved")
        self.reviews.append({"head_sha": head_sha, "body": body, "comments": list(comments)})
        return 900 + len(self.reviews)

    def create_issue_comment(self, repo: str, number: int, body: str) -> int:
        self.comments.append(body)
        return 500 + len(self.comments)

    def add_reaction(self, repo: str, comment_id: int, content: str) -> None:
        self.reactions.append(content)


@dataclass
class FakeLLM:
    replies: list[str]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete_json(
        self, *, model: str, system: str, user: str, max_tokens: int
    ) -> llm.LLMResult:
        self.calls.append({"model": model, "system": system, "user": user})
        text = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        return llm.LLMResult(
            text, model, tokens_in=1000, tokens_out=200, tokens_cached=0, duration_ms=1500
        )


def make_pull(**overrides: Any) -> PullInfo:
    values: dict[str, Any] = {
        "number": 7,
        "title": "Add helper",
        "body": "Adds a helper",
        "html_url": "https://x/pr/7",
        "head_sha": "h" * 40,
        "base_sha": "b" * 40,
        "draft": False,
        "mergeable": True,
        "author_login": "dev",
        "author_type": "User",
        "state": "open",
    }
    values.update(overrides)
    return PullInfo(**values)


@pytest.fixture
def installation(db) -> Installation:
    return Installation.objects.create(
        github_installation_id=111, account_login="acme", account_type="Organization"
    )


@pytest.fixture
def repo(installation) -> Repository:
    return Repository.objects.create(
        installation=installation,
        github_repo_id=222,
        full_name="acme/app",
        default_branch="main",
    )


@pytest.fixture
def indexed_repo(repo) -> Repository:
    repo.index_status = IndexStatus.READY
    repo.indexed_sha = "b" * 40
    repo.save()
    return repo


@pytest.fixture
def user(db, installation) -> User:
    u = User.objects.create(username="octo", github_user_id=1)
    InstallationMember.objects.create(user=u, installation=installation)
    return u


@pytest.fixture
def stranger(db) -> User:
    other = Installation.objects.create(github_installation_id=999, account_login="other")
    u = User.objects.create(username="eve", github_user_id=2)
    InstallationMember.objects.create(user=u, installation=other)
    return u


@pytest.fixture
def client() -> Client:
    return Client()


def sign(body: bytes) -> str:
    digest = hmac.new(settings.GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def post_webhook(
    client: Client,
    event: str,
    payload: dict[str, Any],
    delivery: str = "d-1",
    signature: str | None = None,
):
    body = json.dumps(payload).encode()
    return client.post(
        "/api/github/webhook",
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature if signature is not None else sign(body),
        HTTP_X_GITHUB_EVENT=event,
        HTTP_X_GITHUB_DELIVERY=delivery,
    )

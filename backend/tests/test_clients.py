from __future__ import annotations

import json
from decimal import Decimal
from io import StringIO

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache
from django.core.management import call_command

from apps.github import client as github_client
from apps.github.client import GitHubAPI, GitHubError, GitHubGatewayImpl
from apps.reviews import llm, queue
from apps.reviews.models import Review
from core.schemas import ReviewOutput
from tests.conftest import FakeGateway, FakeLLM, make_pull
from tests.test_pipeline import DIFF, REVIEW_JSON, _install_index


def _gateway(handler) -> GitHubGatewayImpl:
    http = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    return GitHubGatewayImpl(GitHubAPI("token", client=http))


def test_ci_state_aggregation():
    def make(runs, combined):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/check-runs"):
                return httpx.Response(200, json={"check_runs": runs})
            return httpx.Response(200, json=combined)

        return _gateway(handler).get_ci_state("o/r", "sha")

    none = {"total_count": 0, "state": "pending"}
    assert make([], none) == "none"
    assert make([{"status": "completed", "conclusion": "success"}], none) == "success"
    assert make([{"status": "in_progress"}], none) == "pending"
    assert (
        make(
            [
                {"status": "completed", "conclusion": "success"},
                {"status": "completed", "conclusion": "failure"},
            ],
            none,
        )
        == "failure"
    )
    assert make([], {"total_count": 1, "state": "failure"}) == "failure"
    assert make([], {"total_count": 1, "state": "success"}) == "success"


def test_gateway_requests_and_errors():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/contents/.aethos.yml"):
            return httpx.Response(404, json={"message": "Not Found"})
        if request.url.path.endswith("/reviews"):
            return httpx.Response(200, json={"id": 77})
        if request.url.path.endswith("/pulls/9"):
            if request.headers["accept"] == "application/vnd.github.diff":
                return httpx.Response(200, text="diff --git a/x b/x\n")
            return httpx.Response(
                200,
                json={
                    "title": "T",
                    "body": None,
                    "html_url": "u",
                    "draft": True,
                    "mergeable": None,
                    "state": "open",
                    "head": {"sha": "h"},
                    "base": {"sha": "b"},
                    "user": {"login": "dev", "type": "User"},
                },
            )
        return httpx.Response(500, text="boom")

    gateway = _gateway(handler)
    pull = gateway.get_pull("o/r", 9)
    assert (pull.head_sha, pull.base_sha, pull.draft, pull.mergeable, pull.body) == (
        "h",
        "b",
        True,
        None,
        "",
    )
    assert gateway.get_diff("o/r", 9).startswith("diff --git")
    assert gateway.get_file_text("o/r", ".aethos.yml", "main") is None
    assert gateway.create_review("o/r", 9, "h", "body", [{"path": "a", "line": 1}]) == 77
    sent = json.loads(next(r for r in seen if r.url.path.endswith("/reviews")).content)
    assert sent["event"] == "COMMENT" and sent["commit_id"] == "h"
    assert seen[0].headers["authorization"] == "Bearer token"
    with pytest.raises(GitHubError) as exc:
        gateway.add_reaction("o/r", 1, "eyes")
    assert exc.value.status == 500


def test_app_jwt_and_installation_token_cache(settings, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    settings.GITHUB_APP_PRIVATE_KEY = pem
    token = github_client.app_jwt()
    claims = jwt.decode(token, key.public_key(), algorithms=["RS256"])
    assert claims["iss"] == "12345" and claims["exp"] - claims["iat"] <= 600

    calls = []

    def fake_json(self, method, path, **kwargs):
        calls.append(path)
        return {"token": "inst-token"}

    monkeypatch.setattr(GitHubAPI, "json", fake_json)
    cache.clear()
    assert github_client.installation_token(5) == "inst-token"
    assert github_client.installation_token(5) == "inst-token"
    assert calls == ["/app/installations/5/access_tokens"]


def test_qstash_enqueue_publishes_with_dedup(settings, monkeypatch):
    settings.QUEUE_MODE = "qstash"
    settings.QSTASH_TOKEN = "t"
    settings.QSTASH_URL = "https://qstash-us-east-1.upstash.io"
    published = {}

    class FakeMessage:
        def publish_json(self, **kwargs):
            published.update(kwargs)

    class FakeQStash:
        def __init__(self, token, base_url=None):
            published["base_url"] = base_url
            self.message = FakeMessage()

    monkeypatch.setattr(queue, "QStash", FakeQStash)
    queue.enqueue("pack", {"review_id": 3}, "pack:3 x")
    assert published["base_url"] == "https://qstash-us-east-1.upstash.io"
    assert published["url"] == "http://testserver/api/steps/pack"
    assert published["body"] == {"review_id": 3}
    assert published["retries"] == queue.STEP_RETRIES
    assert published["deduplication_id"] == "pack-pack-3-x"


def test_cost_and_output_parsing(settings):
    assert llm.cost_usd("llama-3.3-70b-versatile", 1_000_000, 1_000_000) == Decimal("1.38")
    assert llm.cost_usd("unknown-model", 10, 10) == 0
    fenced = '```json\n{"summary": "ok", "findings": []}\n```'
    assert isinstance(llm.parse_review(fenced), ReviewOutput)
    with pytest.raises(llm.LLMOutputError):
        llm.parse_review('{"summary": 1}')
    with pytest.raises(llm.LLMOutputError):
        llm.parse_review("nope")


def test_compare_command_runs_both_modes_without_posting(monkeypatch, indexed_repo):
    _install_index(indexed_repo)
    gateway = FakeGateway(
        make_pull(), DIFF, files={"app/utils.py": "def helper(x):\n    return x\n" * 400}
    )
    monkeypatch.setattr(github_client, "get_gateway", lambda _id: gateway)
    monkeypatch.setattr(llm, "get_llm", lambda: FakeLLM([REVIEW_JSON]))
    out = StringIO()
    call_command("compare", repo="acme/app", pr=7, stdout=out)
    text = out.getvalue()
    assert "aethos" in text and "baseline" in text
    reviews = {r.mode: r for r in Review.objects.all()}
    assert set(reviews) == {"aethos", "baseline"} and all(r.dry_run for r in reviews.values())
    assert gateway.reviews == [] and gateway.comments == []
    out2 = StringIO()
    call_command("show_review", reviews["aethos"].pk, stdout=out2)
    assert "context pack" in out2.getvalue()

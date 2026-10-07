from __future__ import annotations

import json

import pytest

from apps.github import client as github_client
from apps.indexing import services as index_services
from apps.reviews import llm
from apps.reviews.models import Finding, Review, ReviewMode, ReviewStatus
from tests.conftest import FakeGateway, FakeLLM, make_pull, post_webhook

DIFF = """\
diff --git a/app/utils.py b/app/utils.py
--- a/app/utils.py
+++ b/app/utils.py
@@ -3,4 +3,5 @@ import os
 def helper(x):
-    return x * 2
+    value = x * 2
+    return value


@@ -20,2 +22,3 @@ def other():
     a = 1
+    b = 2
     return a
"""

REVIEW_JSON = json.dumps(
    {
        "summary": "Refactors helper.",
        "walkthrough": [{"path": "app/utils.py", "change": "helper refactor"}],
        "findings": [
            {
                "path": "app/utils.py",
                "line": 5,
                "severity": "high",
                "confidence": 0.9,
                "category": "bug",
                "title": "Overflow possible",
                "body": "x * 2 can overflow.",
                "suggestion": "    value = x * 2  # checked",
            },
            {
                "path": "app/utils.py",
                "line": 23,
                "severity": "medium",
                "confidence": 0.8,
                "category": "performance",
                "title": "Quadratic loop",
                "body": "Use a set.",
            },
            {
                "path": "app/utils.py",
                "line": 400,
                "severity": "low",
                "confidence": 0.9,
                "category": "style",
                "title": "Off diff",
                "body": "Not in the diff.",
            },
            {
                "path": "ghost.py",
                "line": 1,
                "severity": "critical",
                "confidence": 0.99,
                "category": "bug",
                "title": "Hallucinated file",
                "body": "No such file.",
            },
            {
                "path": "app/utils.py",
                "line": 5,
                "severity": "nit",
                "confidence": 0.1,
                "category": "style",
                "title": "Low confidence",
                "body": "meh",
            },
        ],
    }
)


def _install_index(repo) -> None:
    index_services.begin_index(repo, "b" * 40, {"app/utils.py": "a" * 64, "app/main.py": "c" * 64})
    index_services.ingest_files(
        repo,
        "b" * 40,
        [
            index_services.FileIn(
                path="app/utils.py",
                language="python",
                content_hash="a" * 64,
                loc=30,
                is_test=False,
                symbols=[
                    index_services.SymbolIn(
                        "helper", "helper", "function", 3, 5, "def helper(x)", True
                    )
                ],
                chunks=[
                    index_services.ChunkIn(0, 0, "def helper(x):\n    return x * 2", 10, " helper ")
                ],
            ),
            index_services.FileIn(
                path="app/main.py",
                language="python",
                content_hash="c" * 64,
                loc=10,
                is_test=False,
                symbols=[
                    index_services.SymbolIn("main", "main", "function", 1, 3, "def main()", True)
                ],
                chunks=[
                    index_services.ChunkIn(
                        0, 0, "def main():\n    return helper(2)", 8, " main helper "
                    )
                ],
            ),
        ],
    )
    index_services.ingest_edges(
        repo,
        [
            index_services.EdgeIn("calls", "app/main.py", "main", "app/utils.py", "helper", 0.9),
            index_services.EdgeIn("imports", "app/main.py", None, "app/utils.py", None, 1.0),
        ],
        first=True,
    )
    index_services.finalize_index(repo, "b" * 40)
    repo.refresh_from_db()


def _comment_payload(repo, body="@aethos please review", comment_id=42, user_type="User"):
    return {
        "action": "created",
        "repository": {"id": repo.github_repo_id},
        "issue": {"number": 7, "pull_request": {"url": "x"}},
        "comment": {"id": comment_id, "body": body, "user": {"login": "dev", "type": user_type}},
    }


@pytest.fixture
def run(monkeypatch, client, indexed_repo):
    _install_index(indexed_repo)

    def go(gateway: FakeGateway, fake_llm: FakeLLM, payload=None, delivery="d-1"):
        monkeypatch.setattr(github_client, "get_gateway", lambda _id: gateway)
        monkeypatch.setattr(llm, "get_llm", lambda: fake_llm)
        return post_webhook(
            client, "issue_comment", payload or _comment_payload(indexed_repo), delivery=delivery
        )

    return go


def test_full_review_posts_verdict_and_inline_comments(run, indexed_repo):
    gateway = FakeGateway(make_pull(), DIFF, ci_state="success")
    fake = FakeLLM([REVIEW_JSON])
    response = run(gateway, fake)
    assert response.status_code == 202

    review = Review.objects.get()
    assert review.status == ReviewStatus.POSTED
    assert review.verdict == "not_ready"
    assert review.mode == ReviewMode.AETHOS
    assert review.tokens_in == 1000 and review.cost_usd > 0
    assert review.usage.count() == 1
    assert gateway.reactions == ["eyes", "rocket"]

    findings = {f.title: f for f in Finding.objects.filter(review=review)}
    assert set(findings) == {"Overflow possible", "Quadratic loop", "Off diff"}
    assert findings["Overflow possible"].posted_inline
    assert findings["Quadratic loop"].posted_inline
    assert not findings["Off diff"].posted_inline

    posted = gateway.reviews[0]
    assert posted["head_sha"] == "h" * 40
    assert {c["line"] for c in posted["comments"]} == {5, 23}
    assert (
        "```suggestion" in posted["comments"][0]["body"]
        or "```suggestion" in posted["comments"][1]["body"]
    )
    assert "Not ready to merge" in posted["body"]
    assert "Quadratic loop" in posted["body"] and "Bottlenecks" in posted["body"]
    assert "Off diff" in posted["body"]  # detached finding listed in the summary
    assert "helper" in posted["body"] or "dependents" not in posted["body"]


def test_pack_uses_index_context_and_records_dropped_items(run):
    gateway = FakeGateway(make_pull(), DIFF)
    fake = FakeLLM([REVIEW_JSON])
    run(gateway, fake)
    review = Review.objects.get()
    sections = {item["section"] for item in review.pack["items"]}
    assert {"meta", "diff", "symbols", "related"} <= sections
    titles = [i["title"] for i in review.pack["items"]]
    assert any("Caller app/main.py: main" in t for t in titles)
    assert review.pack["meta"]["index_used"] is True
    assert "Caller app/main.py: main" in fake.calls[0]["user"]
    assert "ghost.py" not in review.pack["meta"]["commentable"]


def test_duplicate_delivery_and_retry_create_one_review(run):
    gateway = FakeGateway(make_pull(), DIFF)
    fake = FakeLLM([REVIEW_JSON])
    run(gateway, fake, delivery="same")
    again = run(gateway, fake, delivery="same")
    assert again.json()["status"] == "duplicate"
    assert Review.objects.count() == 1
    assert len(gateway.reviews) == 1 and len(fake.calls) == 1

    # A different delivery for the same comment (e.g. redelivery with a new id) is a no-op too.
    run(gateway, fake, delivery="other")
    assert Review.objects.count() == 1 and len(gateway.reviews) == 1


def test_skipped_prs_cost_nothing_and_get_a_reply(run):
    lock_diff = (
        "diff --git a/package-lock.json b/package-lock.json\n--- a/package-lock.json\n"
        "+++ b/package-lock.json\n@@ -1 +1 @@\n-a\n+b\n"
    )
    gateway = FakeGateway(make_pull(), lock_diff)
    fake = FakeLLM([REVIEW_JSON])
    run(gateway, fake)
    review = Review.objects.get()
    assert review.status == ReviewStatus.SKIPPED and fake.calls == []
    assert gateway.comments and "skipped" in gateway.comments[0].lower()
    assert gateway.reviews == []


def test_bot_authored_pr_is_skipped(run):
    gateway = FakeGateway(make_pull(author_login="dependabot[bot]", author_type="Bot"), DIFF)
    fake = FakeLLM([REVIEW_JSON])
    run(gateway, fake)
    assert Review.objects.get().skip_reason == "PR author is a bot"
    assert fake.calls == []


def test_invalid_model_output_retries_once_then_inconclusive(run):
    gateway = FakeGateway(make_pull(), DIFF)
    fake = FakeLLM(["not json", "still not json"])
    run(gateway, fake)
    review = Review.objects.get()
    assert len(fake.calls) == 2
    assert "invalid" in fake.calls[1]["user"]
    assert review.verdict == "inconclusive"
    assert review.usage.count() == 2


def test_model_recovers_on_retry(run):
    gateway = FakeGateway(make_pull(), DIFF)
    fake = FakeLLM(["{bad", json.dumps({"summary": "Looks fine.", "findings": []})])
    run(gateway, fake)
    review = Review.objects.get()
    assert len(fake.calls) == 2
    assert review.verdict in {"ready", "ready_with_suggestions"}


def test_signals_block_the_merge(run):
    gateway = FakeGateway(make_pull(draft=True, mergeable=False), DIFF, ci_state="failure")
    fake = FakeLLM([json.dumps({"summary": "ok", "findings": []})])
    run(gateway, fake)
    review = Review.objects.get()
    codes = {r["code"] for r in review.verdict_reasons}
    assert review.verdict == "not_ready"
    assert {"draft", "conflicts", "ci_failing"} <= codes


def test_stale_head_posts_nothing(run, monkeypatch):
    gateway = FakeGateway(make_pull(), DIFF)
    fake = FakeLLM([REVIEW_JSON])
    original = gateway.get_pull
    calls = {"n": 0}

    def moving_head(repo, number):
        calls["n"] += 1
        pull = original(repo, number)
        # triage + pack see the original head; the post step sees a newer one
        return make_pull(head_sha="n" * 40) if calls["n"] >= 3 else pull

    gateway.get_pull = moving_head  # type: ignore[method-assign]
    run(gateway, fake)
    review = Review.objects.get()
    assert review.status == ReviewStatus.SUPERSEDED
    assert gateway.reviews == []


def test_github_422_falls_back_to_summary_only(run):
    gateway = FakeGateway(make_pull(), DIFF, reject_inline=True)
    run(gateway, FakeLLM([REVIEW_JSON]))
    review = Review.objects.get()
    assert review.status == ReviewStatus.POSTED
    assert gateway.reviews[0]["comments"] == []
    assert "could not be attached" in gateway.reviews[0]["body"]
    assert not Finding.objects.filter(review=review, posted_inline=True).exists()


def test_baseline_mode_builds_a_larger_unranked_pack(run, indexed_repo):
    indexed_repo.settings = {"mode": "baseline"}
    indexed_repo.save()
    gateway = FakeGateway(
        make_pull(),
        DIFF,
        files={
            "app/utils.py": "def helper(x):\n    return x*2\n" * 50,
            "app/main.py": "from app.utils import helper\n",
        },
    )
    run(gateway, FakeLLM([REVIEW_JSON]))
    review = Review.objects.get()
    assert review.mode == ReviewMode.BASELINE
    sections = {i["section"] for i in review.pack["items"]}
    assert "symbols" in sections and "similar" not in sections


def test_unmentioned_and_bot_comments_are_ignored(run, indexed_repo):
    gateway = FakeGateway(make_pull(), DIFF)
    fake = FakeLLM([REVIEW_JSON])
    run(
        gateway,
        fake,
        payload={
            **_comment_payload(indexed_repo, body="thanks!"),
        },
        delivery="a",
    )
    run(gateway, fake, payload=_comment_payload(indexed_repo, user_type="Bot"), delivery="b")
    run(
        gateway,
        fake,
        payload=_comment_payload(indexed_repo, body="> @aethos review\nthis quoted line"),
        delivery="c",
    )
    assert Review.objects.count() == 0 and fake.calls == []


def test_dry_run_reviews_never_touch_github(monkeypatch, indexed_repo):
    from apps.reviews import pipeline

    _install_index(indexed_repo)
    gateway = FakeGateway(make_pull(), DIFF)
    monkeypatch.setattr(github_client, "get_gateway", lambda _id: gateway)
    monkeypatch.setattr(llm, "get_llm", lambda: FakeLLM([REVIEW_JSON]))
    pipeline.run_step(
        "triage",
        {
            "repo_id": indexed_repo.pk,
            "pr_number": 7,
            "comment_id": 0,
            "dry_run": True,
            "mode": "aethos",
        },
    )
    review = Review.objects.get()
    assert review.dry_run and review.status == ReviewStatus.POSTED and review.verdict
    assert gateway.reviews == [] and gateway.comments == [] and gateway.reactions == []

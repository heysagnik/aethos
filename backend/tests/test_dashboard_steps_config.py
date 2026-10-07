from __future__ import annotations

import json
from decimal import Decimal

from apps.reviews import views as review_views
from apps.reviews.config import ReviewSettings, resolve_settings
from apps.reviews.models import Finding, Review, ReviewMode, ReviewStatus, UsageLog


def _review(repo, **kwargs):
    defaults = {
        "repository": repo,
        "pr_number": 1,
        "pr_title": "t",
        "head_sha": "h" * 40,
        "base_sha": "b" * 40,
        "trigger_comment_id": 1,
        "status": ReviewStatus.POSTED,
        "verdict": "ready",
        "mode": ReviewMode.AETHOS,
        "tokens_in": 1000,
        "tokens_out": 100,
        "cost_usd": Decimal("0.001"),
        "pack": {"items": [], "dropped": []},
    }
    defaults.update(kwargs)
    return Review.objects.create(**defaults)


def test_dashboard_requires_login(client):
    assert client.get("/api/dashboard/overview").status_code == 401
    assert client.get("/api/dashboard/repos").status_code == 401


def test_overview_counts_and_savings(client, user, repo):
    r1 = _review(repo)
    _review(repo, trigger_comment_id=2, pr_number=2, verdict="not_ready")
    _review(repo, trigger_comment_id=3, status=ReviewStatus.SKIPPED, verdict="")
    _review(repo, trigger_comment_id=4, mode=ReviewMode.BASELINE, tokens_in=5000)
    _review(repo, trigger_comment_id=5, pr_number=9, dry_run=True)
    Finding.objects.create(
        review=r1,
        path="a.py",
        line=1,
        severity="high",
        confidence=0.9,
        category="bug",
        title="t",
        body="b",
    )
    client.force_login(user)
    data = client.get("/api/dashboard/overview?days=30").json()
    assert data["reviews_total"] == 3 and data["reviews_posted"] == 2
    assert data["reviews_skipped"] == 1
    assert data["verdicts"]["ready"] == 1 and data["verdicts"]["not_ready"] == 1
    assert data["severities"]["high"] == 1
    assert data["savings"] == {
        "pairs": 1,
        "baseline_tokens_in": 5000,
        "aethos_tokens_in": 1000,
        "saved_pct": 80.0,
    }
    assert data["series"] and data["series"][0]["reviews"] == 3


def test_users_only_see_their_own_installations(client, user, stranger, repo):
    review = _review(repo)
    client.force_login(stranger)
    assert client.get("/api/dashboard/repos").json() == []
    assert client.get(f"/api/dashboard/repos/{repo.pk}").status_code == 404
    assert client.get(f"/api/dashboard/reviews/{review.pk}").status_code == 404
    assert client.get("/api/dashboard/reviews").json() == []
    assert client.get("/api/dashboard/overview").json()["reviews_total"] == 0
    assert (
        client.patch(
            f"/api/dashboard/repos/{repo.pk}/settings",
            data={"max_comments": 5},
            content_type="application/json",
        ).status_code
        == 404
    )


def test_repo_and_review_detail(client, user, repo):
    review = _review(repo, verdict_reasons=[{"code": "x", "text": "t", "blocking": False}])
    UsageLog.objects.create(review=review, step="review", model="m", tokens_in=10, tokens_out=5)
    client.force_login(user)
    repos = client.get("/api/dashboard/repos").json()
    assert repos[0]["full_name"] == "acme/app" and repos[0]["review_count"] == 1
    detail = client.get(f"/api/dashboard/repos/{repo.pk}").json()
    assert detail["full_name"] == "acme/app" and "index_workflow" not in detail
    body = client.get(f"/api/dashboard/reviews/{review.pk}").json()
    assert body["pr_url"] == "https://github.com/acme/app/pull/1"
    assert body["usage"][0]["step"] == "review" and body["pack"] == {"items": [], "dropped": []}


def test_settings_patch_validates_and_persists(client, user, repo):
    client.force_login(user)
    url = f"/api/dashboard/repos/{repo.pk}/settings"
    bad = client.patch(url, data={"pack_tokens": 5}, content_type="application/json")
    assert bad.status_code == 422
    ok = client.patch(
        url, data={"max_comments": 5, "block_on": ["critical"]}, content_type="application/json"
    )
    assert ok.status_code == 200 and ok.json()["settings"]["max_comments"] == 5
    repo.refresh_from_db()
    assert repo.settings == {"max_comments": 5, "block_on": ["critical"]}
    assert repo.effective_settings()["pack_tokens"] == 12000


def test_yaml_overrides_and_invalid_layers_are_ignored():
    yaml_text = (
        "review:\n  max_comments: 3\n  ignore_paths: ['gen/**']\nbudget:\n  pack_tokens: 8000\n"
    )
    cfg = resolve_settings({"min_confidence": 0.7}, yaml_text)
    assert (cfg.max_comments, cfg.pack_tokens, cfg.min_confidence) == (3, 8000, 0.7)
    assert cfg.ignore_paths == ["gen/**"]
    broken = resolve_settings({}, "review:\n  max_comments: 9999\n")
    assert broken.max_comments == ReviewSettings().max_comments
    assert resolve_settings({}, ":::not yaml").max_comments == 15
    assert resolve_settings({"pack_tokens": 1}, None).pack_tokens == 12000


class _Receiver:
    def __init__(self, ok: bool) -> None:
        self.ok = ok

    def verify(self, **kwargs):
        from qstash.errors import SignatureError

        if not self.ok:
            raise SignatureError("bad")


def _steps_client(monkeypatch, settings, ok=True):
    settings.QUEUE_MODE = "qstash"
    monkeypatch.setattr(review_views, "Receiver", lambda **kw: _Receiver(ok))


def test_step_endpoint_rejects_unsigned_and_unknown(client, settings, monkeypatch):
    settings.QUEUE_MODE = "inline"
    assert (
        client.post("/api/steps/triage", data="{}", content_type="application/json").status_code
        == 404
    )
    _steps_client(monkeypatch, settings, ok=False)
    assert (
        client.post("/api/steps/triage", data="{}", content_type="application/json").status_code
        == 401
    )
    _steps_client(monkeypatch, settings, ok=True)
    assert (
        client.post("/api/steps/nope", data="{}", content_type="application/json").status_code
        == 404
    )


def test_step_failures_retry_then_mark_failed(client, settings, monkeypatch, repo):
    _steps_client(monkeypatch, settings)
    review = _review(repo, status=ReviewStatus.PACKED, verdict="")
    monkeypatch.setattr(
        "apps.reviews.pipeline.STEPS",
        {"review": lambda payload: (_ for _ in ()).throw(RuntimeError("boom"))},
    )
    notices = []
    monkeypatch.setattr("apps.reviews.pipeline._notify", lambda *a, **k: notices.append(a))
    monkeypatch.setattr("apps.reviews.pipeline.gateway_for", lambda repo: object())
    body = json.dumps({"review_id": review.pk})

    first = client.post("/api/steps/review", data=body, content_type="application/json")
    assert first.status_code == 500
    last = client.post(
        "/api/steps/review", data=body, content_type="application/json", HTTP_UPSTASH_RETRIED="3"
    )
    assert last.status_code == 200 and last.json() == {"status": "failed"}
    review.refresh_from_db()
    assert review.status == ReviewStatus.FAILED and "boom" in review.error
    assert len(notices) == 1


def test_workspaces_list_and_scope_the_dashboard(client, user, repo):
    from apps.repos.models import Installation, InstallationMember, Repository

    second = Installation.objects.create(github_installation_id=333, account_login="beta-org")
    other_repo = Repository.objects.create(
        installation=second, github_repo_id=444, full_name="beta-org/api"
    )
    InstallationMember.objects.create(user=user, installation=second)
    _review(repo)
    _review(other_repo, trigger_comment_id=2)
    client.force_login(user)

    workspaces = client.get("/api/dashboard/workspaces").json()
    assert [(w["login"], w["repo_count"]) for w in workspaces] == [("acme", 1), ("beta-org", 1)]

    assert len(client.get("/api/dashboard/repos").json()) == 2
    scoped = client.get("/api/dashboard/repos", {"workspace": "Beta-Org"}).json()
    assert [r["full_name"] for r in scoped] == ["beta-org/api"]
    reviews = client.get("/api/dashboard/reviews", {"workspace": "acme"}).json()
    assert [r["repo"] for r in reviews] == ["acme/app"]
    assert client.get("/api/dashboard/overview", {"workspace": "acme"}).json()["reviews_total"] == 1


def test_a_workspace_the_user_does_not_belong_to_is_not_found(client, user, stranger):
    client.force_login(user)
    assert client.get("/api/dashboard/workspaces").json() == [
        {"login": "acme", "account_type": "Organization", "repo_count": 0, "suspended": False}
    ]
    for path in ("overview", "repos", "reviews"):
        assert client.get(f"/api/dashboard/{path}", {"workspace": "other"}).status_code == 404

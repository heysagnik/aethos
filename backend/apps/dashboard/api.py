from __future__ import annotations

from typing import Any

from django.conf import settings
from django.http import Http404, HttpRequest
from ninja import NinjaAPI, Schema
from ninja.security import django_auth
from pydantic import Field, ValidationError

from apps.accounts.models import User
from apps.dashboard import selectors
from apps.indexing.embeddings import embedding_progress
from apps.repos.models import Installation, Repository
from apps.reviews.config import ReviewSettings
from apps.reviews.models import Review
from core.schemas import Severity

api = NinjaAPI(urls_namespace="dashboard", docs_url=None, openapi_url=None, auth=django_auth)

WORKFLOW_TEMPLATE = """name: Aethos index
on:
  push:
    branches: [{branch}]
  workflow_dispatch:
permissions:
  contents: read
  id-token: write
jobs:
  index:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 1
      - uses: {action_repo}@main
        with:
          api-url: {api_url}
"""


def _user(request: HttpRequest) -> User:
    return request.user  # type: ignore[return-value]


def _repo_or_404(request: HttpRequest, repo_id: int) -> Repository:
    repo = selectors.repos_for_user(_user(request)).filter(pk=repo_id).first()
    if repo is None:
        raise Http404
    return repo


def _workspace_or_404(request: HttpRequest, login: str | None) -> Installation | None:
    """The requested workspace, which must be one the user belongs to; None means all of them."""
    if not login:
        return None
    workspace = selectors.workspace_for_user(_user(request), login)
    if workspace is None:
        raise Http404
    return workspace


class WorkspaceOut(Schema):
    login: str
    account_type: str
    repo_count: int
    suspended: bool


class VerdictCounts(Schema):
    ready: int
    ready_with_suggestions: int
    not_ready: int
    inconclusive: int


class SeverityCounts(Schema):
    critical: int
    high: int
    medium: int
    low: int
    nit: int


class SeriesPoint(Schema):
    date: str
    reviews: int
    cost_usd: float


class Savings(Schema):
    pairs: int
    baseline_tokens_in: int
    aethos_tokens_in: int
    saved_pct: float | None


class OverviewOut(Schema):
    days: int
    reviews_total: int
    reviews_posted: int
    reviews_skipped: int
    verdicts: VerdictCounts
    severities: SeverityCounts
    tokens_in: int
    tokens_out: int
    cost_usd: float
    series: list[SeriesPoint]
    savings: Savings


class RepoOut(Schema):
    id: int
    full_name: str
    is_private: bool
    default_branch: str
    index_status: str
    indexed_sha: str
    last_indexed_at: str | None
    file_count: int
    symbol_count: int
    edge_count: int
    chunk_count: int
    embedded_count: int
    review_count: int
    settings: dict[str, Any]


class ReviewListItem(Schema):
    id: int
    repo_id: int
    repo: str
    pr_number: int
    pr_title: str
    pr_url: str
    status: str
    verdict: str
    mode: str
    risk: str
    skip_reason: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    created_at: str


class FindingOut(Schema):
    path: str
    line: int
    severity: str
    confidence: float
    category: str
    title: str
    body: str
    suggestion: str
    posted_inline: bool


class UsageOut(Schema):
    step: str
    model: str
    tokens_in: int
    tokens_out: int
    tokens_cached: int
    cost_usd: float
    duration_ms: int


class ReviewDetail(ReviewListItem):
    summary: str
    verdict_reasons: list[dict[str, Any]]
    findings: list[FindingOut]
    usage: list[UsageOut]
    pack: dict[str, Any] | None
    instructions: str
    error: str


class RepoDetail(RepoOut):
    index_workflow: str


class SettingsPatch(Schema):
    enabled: bool | None = None
    mode: str | None = None
    pack_tokens: int | None = None
    max_comments: int | None = None
    min_confidence: float | None = None
    ignore_paths: list[str] | None = Field(default=None, max_length=100)
    high_risk_paths: list[str] | None = Field(default=None, max_length=100)
    block_on: list[Severity] | None = None


def _repo_out(repo: Repository, review_count: int) -> dict[str, Any]:
    embedded, chunks = embedding_progress(repo.pk)
    return {
        "id": repo.pk,
        "full_name": repo.full_name,
        "is_private": repo.is_private,
        "default_branch": repo.default_branch,
        "index_status": repo.index_status,
        "indexed_sha": repo.indexed_sha,
        "last_indexed_at": repo.last_indexed_at.isoformat() if repo.last_indexed_at else None,
        "file_count": repo.file_count,
        "symbol_count": repo.symbol_count,
        "edge_count": repo.edge_count,
        "chunk_count": chunks,
        "embedded_count": embedded,
        "review_count": review_count,
        "settings": ReviewSettings.model_validate(repo.effective_settings()).model_dump(
            mode="json"
        ),
    }


def _review_item(review: Review) -> dict[str, Any]:
    repo = review.repository
    return {
        "id": review.pk,
        "repo_id": repo.pk,
        "repo": repo.full_name,
        "pr_number": review.pr_number,
        "pr_title": review.pr_title,
        "pr_url": f"https://github.com/{repo.full_name}/pull/{review.pr_number}",
        "status": review.status,
        "verdict": review.verdict,
        "mode": review.mode,
        "risk": review.risk,
        "skip_reason": review.skip_reason,
        "tokens_in": review.tokens_in,
        "tokens_out": review.tokens_out,
        "cost_usd": float(review.cost_usd),
        "latency_ms": review.latency_ms,
        "created_at": review.created_at.isoformat(),
    }


@api.get("/workspaces", response=list[WorkspaceOut], url_name="workspaces")
def workspaces(request: HttpRequest) -> list[dict[str, Any]]:
    from django.db.models import Count, Q

    rows = (
        selectors.installations_for_user(_user(request))
        .annotate(n=Count("repositories", filter=Q(repositories__removed_at__isnull=True)))
        .order_by("account_login")
    )
    return [
        {
            "login": i.account_login,
            "account_type": i.account_type,
            "repo_count": i.n,
            "suspended": i.suspended_at is not None,
        }
        for i in rows
    ]


@api.get("/overview", response=OverviewOut, url_name="overview")
def overview(request: HttpRequest, days: int = 30, workspace: str = "") -> dict[str, Any]:
    scope = _workspace_or_404(request, workspace)
    return selectors.overview(_user(request), max(1, min(days, 365)), scope)


@api.get("/repos", response=list[RepoOut], url_name="repos")
def repos(request: HttpRequest, workspace: str = "") -> list[dict[str, Any]]:
    from django.db.models import Count

    scope = _workspace_or_404(request, workspace)
    queryset = (
        selectors.repos_for_user(_user(request), scope)
        .annotate(n=Count("reviews"))
        .order_by("full_name")
    )
    return [_repo_out(r, r.n) for r in queryset]


@api.get("/repos/{repo_id}", response=RepoDetail, url_name="repo")
def repo_detail(request: HttpRequest, repo_id: int) -> dict[str, Any]:
    repo = _repo_or_404(request, repo_id)
    data = _repo_out(repo, repo.reviews.count())
    data["index_workflow"] = WORKFLOW_TEMPLATE.format(
        branch=repo.default_branch,
        action_repo=settings.INDEXER_ACTION_REPO,
        api_url=settings.APP_BASE_URL,
    )
    return data


@api.patch("/repos/{repo_id}/settings", response=RepoOut, url_name="repo-settings")
def update_settings(request: HttpRequest, repo_id: int, body: SettingsPatch) -> dict[str, Any]:
    repo = _repo_or_404(request, repo_id)
    patch = body.model_dump(exclude_unset=True, exclude_none=True)
    if "block_on" in patch:
        patch["block_on"] = [s.value for s in patch["block_on"]]
    merged = {**repo.settings, **patch}
    try:
        ReviewSettings.model_validate({**repo.effective_settings(), **patch})
    except ValidationError as exc:
        from ninja.errors import HttpError

        raise HttpError(422, str(exc.errors()[0]["msg"])) from exc
    repo.settings = {k: v for k, v in merged.items() if k in ReviewSettings.model_fields}
    repo.save(update_fields=["settings"])
    return _repo_out(repo, repo.reviews.count())


@api.get("/reviews", response=list[ReviewListItem], url_name="reviews")
def reviews(
    request: HttpRequest,
    repo_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    workspace: str = "",
) -> list[dict[str, Any]]:
    scope = _workspace_or_404(request, workspace)
    queryset = selectors.reviews_for_user(_user(request), scope).filter(dry_run=False)
    if repo_id is not None:
        queryset = queryset.filter(repository_id=repo_id)
    page = queryset.order_by("-created_at")[
        max(0, offset) : max(0, offset) + max(1, min(limit, 100))
    ]
    return [_review_item(r) for r in page]


@api.get("/reviews/{review_id}", response=ReviewDetail, url_name="review")
def review_detail(request: HttpRequest, review_id: int) -> dict[str, Any]:
    review = selectors.reviews_for_user(_user(request)).filter(pk=review_id).first()
    if review is None:
        raise Http404
    data = _review_item(review)
    data.update(
        {
            "summary": review.summary,
            "verdict_reasons": review.verdict_reasons,
            "findings": [
                {
                    "path": f.path,
                    "line": f.line,
                    "severity": f.severity,
                    "confidence": f.confidence,
                    "category": f.category,
                    "title": f.title,
                    "body": f.body,
                    "suggestion": f.suggestion,
                    "posted_inline": f.posted_inline,
                }
                for f in review.findings.order_by("-confidence", "path", "line")
            ],
            "usage": [
                {
                    "step": u.step,
                    "model": u.model,
                    "tokens_in": u.tokens_in,
                    "tokens_out": u.tokens_out,
                    "tokens_cached": u.tokens_cached,
                    "cost_usd": float(u.cost_usd),
                    "duration_ms": u.duration_ms,
                }
                for u in review.usage.order_by("id")
            ],
            "pack": review.pack,
            "instructions": review.instructions,
            "error": review.error,
        }
    )
    return data

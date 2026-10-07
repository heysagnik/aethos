"""Read queries for the dashboard. Everything is scoped to the requesting user."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Count, QuerySet, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.accounts.models import User
from apps.repos.models import Repository
from apps.reviews.models import Finding, Review, ReviewMode, ReviewStatus

PAIR_SCAN_LIMIT = 500


def repos_for_user(user: User) -> QuerySet[Repository]:
    return Repository.objects.filter(installation__members__user=user).distinct()


def reviews_for_user(user: User) -> QuerySet[Review]:
    return Review.objects.filter(repository__in=repos_for_user(user)).select_related("repository")


def overview(user: User, days: int) -> dict[str, Any]:
    since = timezone.now() - timedelta(days=days)
    base = reviews_for_user(user).filter(created_at__gte=since, dry_run=False)
    mine = base.filter(mode=ReviewMode.AETHOS)
    posted = mine.filter(status=ReviewStatus.POSTED)

    verdicts = dict.fromkeys(("ready", "ready_with_suggestions", "not_ready", "inconclusive"), 0)
    for row in posted.values("verdict").annotate(n=Count("id")):
        if row["verdict"] in verdicts:
            verdicts[row["verdict"]] = row["n"]

    severities = dict.fromkeys(("critical", "high", "medium", "low", "nit"), 0)
    finding_rows = (
        Finding.objects.filter(review__in=posted).values("severity").annotate(n=Count("id"))
    )
    for sev_row in finding_rows:
        if sev_row["severity"] in severities:
            severities[sev_row["severity"]] = sev_row["n"]

    totals = mine.aggregate(tin=Sum("tokens_in"), tout=Sum("tokens_out"), cost=Sum("cost_usd"))
    series = [
        {"date": row["day"].isoformat(), "reviews": row["n"], "cost_usd": float(row["cost"] or 0)}
        for row in mine.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(n=Count("id"), cost=Sum("cost_usd"))
        .order_by("day")
    ]
    return {
        "days": days,
        "reviews_total": mine.count(),
        "reviews_posted": posted.count(),
        "reviews_skipped": mine.filter(status=ReviewStatus.SKIPPED).count(),
        "verdicts": verdicts,
        "severities": severities,
        "tokens_in": totals["tin"] or 0,
        "tokens_out": totals["tout"] or 0,
        "cost_usd": float(totals["cost"] or 0),
        "series": series,
        "savings": savings(base),
    }


def savings(reviews: QuerySet[Review]) -> dict[str, Any]:
    """Input tokens: Aethos vs. baseline for the same PR head, where both were run."""
    baselines = reviews.filter(mode=ReviewMode.BASELINE, tokens_in__gt=0)[:PAIR_SCAN_LIMIT]
    baseline_tokens = aethos_tokens = pairs = 0
    for baseline in baselines:
        match = (
            reviews.filter(
                mode=ReviewMode.AETHOS,
                repository_id=baseline.repository_id,
                pr_number=baseline.pr_number,
                head_sha=baseline.head_sha,
                tokens_in__gt=0,
            )
            .order_by("-created_at")
            .first()
        )
        if match is None:
            continue
        pairs += 1
        baseline_tokens += baseline.tokens_in
        aethos_tokens += match.tokens_in
    saved_pct = (
        round(100 * (baseline_tokens - aethos_tokens) / baseline_tokens, 1) if pairs else None
    )
    return {
        "pairs": pairs,
        "baseline_tokens_in": baseline_tokens,
        "aethos_tokens_in": aethos_tokens,
        "saved_pct": saved_pct,
    }

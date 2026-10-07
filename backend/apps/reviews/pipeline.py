"""The review pipeline: triage -> pack -> review -> post. Each step is short and idempotent."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum

from apps.github import client as github_client
from apps.github.client import GitHubError, GitHubGateway, PullInfo
from apps.repos.models import Repository
from apps.reviews import context, llm
from apps.reviews.config import CONFIG_FILE, ReviewSettings, resolve_settings
from apps.reviews.models import Finding, Review, ReviewMode, ReviewStatus, UsageLog
from apps.reviews.queue import enqueue, inline_steps
from core.diff import DiffParseError, FileDiff, parse_unified_diff
from core.pack import ContextPack, build_pack, render_pack
from core.prompts import SYSTEM_PROMPT, build_user_message
from core.render import (
    FindingView,
    SummaryView,
    inline_comment_body,
    notice_markdown,
    summary_markdown,
)
from core.schemas import SEVERITY_RANK, ReviewOutput, Severity
from core.triage import reviewable_files, triage
from core.verdict import FindingSignal, VerdictInputs, compute_verdict

logger = logging.getLogger(__name__)

BASELINE_SHARES = {
    "meta": 1.0,
    "diff": 0.30,
    "symbols": 0.40,
    "related": 0.30,
    "similar": 0.0,
    "tests": 0.0,
    "map": 0.0,
}
MAX_INSTRUCTIONS_CHARS = 500


class StepError(Exception):
    """A step cannot proceed and retrying will not help."""


def gateway_for(repo: Repository) -> GitHubGateway:
    return github_client.get_gateway(repo.installation.github_installation_id)


def _load_settings(repo: Repository, gateway: GitHubGateway) -> ReviewSettings:
    yaml_text = None
    try:
        yaml_text = gateway.get_file_text(repo.full_name, CONFIG_FILE, repo.default_branch)
    except GitHubError:
        logger.info("Could not read %s for %s", CONFIG_FILE, repo.full_name)
    return resolve_settings(repo.settings, yaml_text)


def _log_usage(review: Review, step: str, result: llm.LLMResult) -> None:
    UsageLog.objects.create(
        review=review,
        step=step,
        model=result.model,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        tokens_cached=result.tokens_cached,
        cost_usd=llm.cost_usd(result.model, result.tokens_in, result.tokens_out),
        duration_ms=result.duration_ms,
    )


def _finish_totals(review: Review) -> None:
    totals = review.usage.aggregate(
        tin=Sum("tokens_in"),
        tout=Sum("tokens_out"),
        cached=Sum("tokens_cached"),
        cost=Sum("cost_usd"),
        ms=Sum("duration_ms"),
    )
    review.tokens_in = totals["tin"] or 0
    review.tokens_out = totals["tout"] or 0
    review.tokens_cached = totals["cached"] or 0
    review.cost_usd = totals["cost"] or Decimal(0)
    review.latency_ms = totals["ms"] or 0


def _notify(repo: Repository, gateway: GitHubGateway, number: int, title: str, detail: str) -> None:
    try:
        gateway.create_issue_comment(repo.full_name, number, notice_markdown(title, detail))
    except GitHubError:
        logger.exception("Could not post notice on %s#%s", repo.full_name, number)


def _react(gateway: GitHubGateway, repo: Repository, comment_id: int, content: str) -> None:
    if comment_id <= 0:
        return
    try:
        gateway.add_reaction(repo.full_name, comment_id, content)
    except GitHubError:
        logger.info("Reaction failed for comment %s", comment_id)


def _fetch_files(gateway: GitHubGateway, review: Review) -> list[FileDiff]:
    diff_text = gateway.get_diff(review.repository.full_name, review.pr_number)
    return parse_unified_diff(diff_text)


# --- steps ------------------------------------------------------------------


def step_triage(payload: dict[str, Any]) -> None:
    repo = Repository.objects.select_related("installation").get(pk=payload["repo_id"])
    gateway = gateway_for(repo)
    number = int(payload["pr_number"])
    comment_id = int(payload.get("comment_id", 0))
    pull = gateway.get_pull(repo.full_name, number)
    cfg = _load_settings(repo, gateway)
    mode = payload.get("mode") or cfg.mode

    try:
        with transaction.atomic():
            review, created = Review.objects.get_or_create(
                repository=repo,
                pr_number=number,
                head_sha=pull.head_sha,
                trigger_comment_id=comment_id,
                mode=mode,
                defaults={
                    "base_sha": pull.base_sha,
                    "pr_title": pull.title[:512],
                    "requested_by": str(payload.get("requested_by", ""))[:255],
                    "instructions": str(payload.get("instructions", ""))[:MAX_INSTRUCTIONS_CHARS],
                    "dry_run": bool(payload.get("dry_run", False)),
                    "config": cfg.model_dump(mode="json"),
                },
            )
    except IntegrityError:  # concurrent duplicate delivery
        return
    if not created and review.status != ReviewStatus.QUEUED:
        return

    if not payload.get("dry_run"):
        _react(gateway, repo, comment_id, "eyes")

    try:
        files = _fetch_files(gateway, review)
    except (GitHubError, DiffParseError) as exc:
        _skip(review, gateway, "The diff is too large or could not be read from GitHub.", str(exc))
        return

    result = triage(
        files,
        author_login=pull.author_login,
        author_type=pull.author_type,
        config=cfg.triage_config(),
    )
    review.risk = result.risk.value
    if result.skip:
        _skip(review, gateway, result.reason or "Skipped")
        return
    review.status = ReviewStatus.TRIAGED
    review.save()
    enqueue("pack", {"review_id": review.pk}, f"pack-{review.pk}")


def _skip(review: Review, gateway: GitHubGateway, reason: str, error: str = "") -> None:
    review.status = ReviewStatus.SKIPPED
    review.skip_reason = reason
    review.error = error[:1000]
    review.save()
    if not review.dry_run:
        _notify(review.repository, gateway, review.pr_number, "Review skipped", reason)


def step_pack(payload: dict[str, Any]) -> None:
    review = Review.objects.select_related("repository__installation").get(pk=payload["review_id"])
    if review.status != ReviewStatus.TRIAGED:
        return
    repo = review.repository
    gateway = gateway_for(repo)
    cfg = ReviewSettings.model_validate(review.config)
    pull = gateway.get_pull(repo.full_name, review.pr_number)
    files = reviewable_files(_fetch_files(gateway, review), cfg.triage_config())

    if review.mode == ReviewMode.BASELINE:
        cands = context.build_baseline_candidates(
            repo=repo,
            files=files,
            pr_title=pull.title,
            pr_body=pull.body,
            author=pull.author_login,
            instructions=review.instructions,
            head_sha=review.head_sha,
            gateway=gateway,
        )
        budget, shares = cfg.baseline_pack_tokens, BASELINE_SHARES
    else:
        cands = context.build_aethos_candidates(
            repo=repo,
            files=files,
            pr_title=pull.title,
            pr_body=pull.body,
            author=pull.author_login,
            instructions=review.instructions,
            base_sha=review.base_sha,
            fan_in_threshold=cfg.fan_in_threshold,
        )
        budget, shares = cfg.pack_tokens, None

    source_lines, tests_changed = context.source_stats(files)
    cands.meta.update(
        {
            "commentable": context.commentable_map(files),
            "source_lines_changed": source_lines,
            "tests_changed": tests_changed,
            "files": [f.path for f in files],
        }
    )
    pack = build_pack(cands.items, budget, shares=shares, meta=cands.meta)
    review.pack = pack.to_dict()
    review.status = ReviewStatus.PACKED
    review.save()
    enqueue("review", {"review_id": review.pk}, f"review-{review.pk}")


def _pack_from_review(review: Review) -> ContextPack:
    data = review.pack or {}
    from core.pack import PackItem

    pack = ContextPack(budget=int(data.get("budget", 0)), meta=dict(data.get("meta", {})))
    pack.items = [
        PackItem(i["section"], i["title"], i["text"], i["reason"], order=n)
        for n, i in enumerate(data.get("items", []))
    ]
    return pack


def _call_model(review: Review, pack_text: str) -> ReviewOutput | None:
    client = llm.get_llm()
    user = build_user_message(pack_text, review.instructions)
    error: str | None = None
    for attempt in range(2):
        message = (
            user
            if error is None
            else (
                f"{user}\n\nYour previous reply was invalid: {error}\nReturn corrected JSON only."
            )
        )
        result = client.complete_json(
            model=settings.REVIEW_MODEL,
            system=SYSTEM_PROMPT,
            user=message,
            max_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
        )
        _log_usage(review, "review" if attempt == 0 else "review-retry", result)
        if result.truncated:
            error = "the output was cut off; return a shorter review"
            continue
        try:
            return llm.parse_review(result.text)
        except llm.LLMOutputError as exc:
            error = str(exc)
    logger.warning("Review %s: model output invalid after retry: %s", review.pk, error)
    return None


def _ranges_contain(ranges: list[list[int]], line: int) -> bool:
    return any(start <= line <= end for start, end in ranges)


def _select_findings(output: ReviewOutput, review: Review, cfg: ReviewSettings) -> list[Finding]:
    commentable: dict[str, list[list[int]]] = (
        (review.pack or {}).get("meta", {}).get("commentable", {})
    )
    seen: set[tuple[str, int, str]] = set()
    kept = []
    for f in output.findings:
        key = (f.path, f.line, f.title)
        if f.path not in commentable or f.confidence < cfg.min_confidence or key in seen:
            continue
        seen.add(key)
        kept.append(f)
    kept.sort(key=lambda f: (-SEVERITY_RANK[f.severity], -f.confidence, f.path, f.line))
    rows = []
    for f in kept[: cfg.max_comments]:
        ranges = commentable[f.path]
        start = f.start_line
        valid_range = start is None or (start <= f.line and _ranges_contain(ranges, start))
        rows.append(
            Finding(
                review=review,
                path=f.path,
                line=f.line,
                start_line=start if valid_range else None,
                severity=f.severity.value,
                confidence=f.confidence,
                category=f.category,
                title=f.title,
                body=f.body,
                suggestion=(f.suggestion or "") if valid_range else "",
            )
        )
    return rows


def step_review(payload: dict[str, Any]) -> None:
    review = Review.objects.select_related("repository__installation").get(pk=payload["review_id"])
    if review.status != ReviewStatus.PACKED:
        return
    cfg = ReviewSettings.model_validate(review.config)
    pack = _pack_from_review(review)
    output = _call_model(review, render_pack(pack))

    with transaction.atomic():
        review.findings.all().delete()
        if output is not None:
            Finding.objects.bulk_create(_select_findings(output, review, cfg))
            review.summary = output.summary
            review.config = {
                **review.config,
                "walkthrough": [[w.path, w.change] for w in output.walkthrough][:30],
            }
        else:
            review.config = {**review.config, "llm_ok": False}
        _finish_totals(review)
        review.status = ReviewStatus.REVIEWED
        review.save()
    enqueue("post", {"review_id": review.pk}, f"post-{review.pk}")


def _finding_views(
    findings: list[Finding], commentable: dict[str, list[list[int]]]
) -> list[FindingView]:
    views = []
    for f in findings:
        ranges = commentable.get(f.path, [])
        inline = _ranges_contain(ranges, f.line)
        views.append(
            FindingView(
                f.path,
                f.line,
                f.start_line,
                f.severity,
                f.category,
                f.title,
                f.body,
                f.suggestion,
                inline,
            )
        )
    return views


def _footer(review: Review, pack: dict[str, Any]) -> str:
    meta = pack.get("meta", {})
    used = pack.get("tokens_used", 0)
    budget = pack.get("budget", 0)
    index = (
        f"index {str(meta.get('index_sha', ''))[:7]}"
        + (" (older than base)" if meta.get("index_stale") else "")
        if meta.get("index_used")
        else "no index"
    )
    return (
        f"Mode {review.mode} · context {used:,}/{budget:,} tokens · {index} · "
        f"LLM {review.tokens_in:,} in / {review.tokens_out:,} out · "
        f"${review.cost_usd:.4f} · {review.latency_ms / 1000:.1f}s"
    )


def step_post(payload: dict[str, Any]) -> None:
    review = Review.objects.select_related("repository__installation").get(pk=payload["review_id"])
    if review.status != ReviewStatus.REVIEWED:
        return
    repo = review.repository
    cfg = ReviewSettings.model_validate(review.config)
    pack = review.pack or {}
    meta = pack.get("meta", {})
    commentable = meta.get("commentable", {})
    findings = list(review.findings.order_by("-confidence", "path", "line"))

    ci_state, mergeable, draft = "unknown", None, False
    gateway: GitHubGateway | None = None
    pull: PullInfo | None = None
    if not review.dry_run:
        gateway = gateway_for(repo)
        pull = gateway.get_pull(repo.full_name, review.pr_number)
        if pull.head_sha != review.head_sha:
            review.status = ReviewStatus.SUPERSEDED
            review.save()
            return
        mergeable, draft = pull.mergeable, pull.draft
        try:
            ci_state = gateway.get_ci_state(repo.full_name, review.head_sha)
        except GitHubError:
            ci_state = "unknown"

    result = compute_verdict(
        VerdictInputs(
            findings=tuple(
                FindingSignal(Severity(f.severity), f.confidence, f.category, f.title)
                for f in findings
            ),
            is_draft=draft,
            mergeable=mergeable,
            ci_state=ci_state,
            source_lines_changed=int(meta.get("source_lines_changed", 0)),
            tests_changed=bool(meta.get("tests_changed", False)),
            high_fan_in=tuple(meta.get("high_fan_in", [])),
            coverage_complete=bool(pack.get("diff_complete", True)),
            llm_ok=review.config.get("llm_ok", True),
        ),
        cfg.verdict_config(),
    )
    views = _finding_views(findings, commentable)
    notes = []
    if meta.get("index_stale"):
        notes.append(
            "The code index is older than this PR's base commit, so related-code context "
            "may be slightly out of date."
        )
    if not meta.get("index_used") and review.mode == ReviewMode.AETHOS:
        notes.append(
            "No code index is available for this repository yet, so only the diff was used. "
            "See the dashboard to set up indexing."
        )
    summary = SummaryView(
        verdict=result.verdict,
        reasons=result.reasons,
        summary=review.summary,
        findings=tuple(views),
        walkthrough=tuple((p, c) for p, c in review.config.get("walkthrough", [])),
        blast_radius=tuple(meta.get("high_fan_in", [])),
        footer=_footer(review, pack),
        notes=notes,
    )
    body = summary_markdown(summary)
    comments = [_comment_payload(f, v) for f, v in zip(findings, views, strict=True) if v.inline]

    review.verdict = result.verdict.value
    review.verdict_reasons = [
        {"code": r.code, "text": r.text, "blocking": r.blocking} for r in result.reasons
    ]
    if review.dry_run or gateway is None:
        review.status = ReviewStatus.POSTED
        review.save()
        return

    review_id = _submit_review(gateway, review, body, comments)
    posted_paths = {(c["path"], c["line"]) for c in comments} if review_id else set()
    Finding.objects.filter(review=review).update(posted_inline=False)
    for f, v in zip(findings, views, strict=True):
        if v.inline and (f.path, f.line) in posted_paths:
            Finding.objects.filter(pk=f.pk).update(posted_inline=True)
    review.github_review_id = review_id
    review.status = ReviewStatus.POSTED
    review.save()
    _react(gateway, repo, review.trigger_comment_id, "rocket")


def _comment_payload(finding: Finding, view: FindingView) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": finding.path,
        "line": finding.line,
        "side": "RIGHT",
        "body": inline_comment_body(view),
    }
    if finding.start_line and finding.start_line < finding.line:
        payload["start_line"] = finding.start_line
        payload["start_side"] = "RIGHT"
    return payload


def _submit_review(
    gateway: GitHubGateway, review: Review, body: str, comments: list[dict[str, Any]]
) -> int | None:
    repo = review.repository
    try:
        return gateway.create_review(
            repo.full_name, review.pr_number, review.head_sha, body, comments
        )
    except GitHubError as exc:
        if exc.status != 422 or not comments:
            raise
    logger.warning("GitHub rejected inline comments for review %s; posting summary only", review.pk)
    comments.clear()
    fallback = body + "\n> Some inline comments could not be attached; see the findings above.\n"
    return gateway.create_review(repo.full_name, review.pr_number, review.head_sha, fallback, [])


# --- dispatch ----------------------------------------------------------------

STEPS = {
    "triage": step_triage,
    "pack": step_pack,
    "review": step_review,
    "post": step_post,
}


def run_step(step: str, payload: dict[str, Any]) -> None:
    handler = STEPS.get(step)
    if handler is None:
        raise StepError(f"Unknown step: {step}")
    handler(payload)


def run_step_chain(step: str, payload: dict[str, Any]) -> None:
    """Run `step` and every step it triggers in this process, bypassing the queue."""
    with inline_steps():
        run_step(step, payload)


def mark_failed(step: str, payload: dict[str, Any], error: str) -> None:
    """Called after QStash exhausted its retries for `step`."""
    review = None
    if "review_id" in payload:
        review = (
            Review.objects.select_related("repository__installation")
            .filter(pk=payload["review_id"])
            .first()
        )
    elif step == "triage":
        review = (
            Review.objects.select_related("repository__installation")
            .filter(
                repository_id=int(payload.get("repo_id", 0)),
                pr_number=int(payload.get("pr_number", 0)),
                trigger_comment_id=int(payload.get("comment_id", 0)),
                status=ReviewStatus.QUEUED,
            )
            .first()
        )
    if review is not None:
        review.status = ReviewStatus.FAILED
        review.error = error[:1000]
        review.save()
        if not review.dry_run:
            _notify(
                review.repository,
                gateway_for(review.repository),
                review.pr_number,
                "Review failed",
                "Something went wrong while reviewing this pull request. "
                "Comment `@" + settings.GITHUB_APP_SLUG + "` again to retry.",
            )

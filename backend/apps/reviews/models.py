from __future__ import annotations

from django.db import models

from apps.repos.models import Repository


class ReviewStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    TRIAGED = "triaged", "Triaged"
    PACKED = "packed", "Packed"
    REVIEWED = "reviewed", "Reviewed"
    POSTED = "posted", "Posted"
    SKIPPED = "skipped", "Skipped"
    SUPERSEDED = "superseded", "Superseded"
    FAILED = "failed", "Failed"


class ReviewMode(models.TextChoices):
    AETHOS = "aethos", "Aethos"
    BASELINE = "baseline", "Baseline"


class Review(models.Model):
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name="reviews")
    pr_number = models.IntegerField()
    pr_title = models.CharField(max_length=512, blank=True)
    head_sha = models.CharField(max_length=64)
    base_sha = models.CharField(max_length=64, blank=True)
    trigger_comment_id = models.BigIntegerField()
    requested_by = models.CharField(max_length=255, blank=True)
    instructions = models.TextField(blank=True)
    mode = models.CharField(max_length=16, choices=ReviewMode.choices, default=ReviewMode.AETHOS)
    dry_run = models.BooleanField(default=False)

    status = models.CharField(
        max_length=16, choices=ReviewStatus.choices, default=ReviewStatus.QUEUED
    )
    skip_reason = models.TextField(blank=True)
    error = models.TextField(blank=True)
    risk = models.CharField(max_length=16, blank=True)

    verdict = models.CharField(max_length=32, blank=True)
    verdict_reasons = models.JSONField(default=list, blank=True)
    summary = models.TextField(blank=True)

    pack = models.JSONField(null=True, blank=True)
    config = models.JSONField(default=dict, blank=True)
    github_review_id = models.BigIntegerField(null=True, blank=True)

    tokens_in = models.IntegerField(default=0)
    tokens_out = models.IntegerField(default=0)
    tokens_cached = models.IntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    latency_ms = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["repository", "pr_number", "head_sha", "trigger_comment_id", "mode"],
                name="uniq_review_per_trigger",
            )
        ]
        indexes = [models.Index(fields=["repository", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.repository.full_name}#{self.pr_number} [{self.status}]"


class Finding(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="findings")
    path = models.CharField(max_length=1024)
    line = models.IntegerField()
    start_line = models.IntegerField(null=True, blank=True)
    severity = models.CharField(max_length=16)
    confidence = models.FloatField()
    category = models.CharField(max_length=32)
    title = models.CharField(max_length=255)
    body = models.TextField()
    suggestion = models.TextField(blank=True)
    posted_inline = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["review"])]


class UsageLog(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="usage")
    step = models.CharField(max_length=32)
    model = models.CharField(max_length=128, blank=True)
    tokens_in = models.IntegerField(default=0)
    tokens_out = models.IntegerField(default=0)
    tokens_cached = models.IntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    duration_ms = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

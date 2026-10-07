from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models


class Installation(models.Model):
    github_installation_id = models.BigIntegerField(unique=True)
    account_login = models.CharField(max_length=255)
    account_type = models.CharField(max_length=32, default="User")
    suspended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.account_login} ({self.github_installation_id})"


class InstallationMember(models.Model):
    """A user who has been verified (via GitHub) to have access to an installation."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    installation = models.ForeignKey(Installation, on_delete=models.CASCADE, related_name="members")
    verified_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "installation"], name="uniq_member_per_installation"
            )
        ]


class IndexStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    INDEXING = "indexing", "Indexing"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"


class Repository(models.Model):
    installation = models.ForeignKey(
        Installation, on_delete=models.CASCADE, related_name="repositories"
    )
    github_repo_id = models.BigIntegerField(unique=True)
    full_name = models.CharField(max_length=255)
    default_branch = models.CharField(max_length=255, default="main")
    is_private = models.BooleanField(default=False)
    removed_at = models.DateTimeField(null=True, blank=True)

    settings = models.JSONField(default=dict, blank=True)

    index_status = models.CharField(
        max_length=16, choices=IndexStatus.choices, default=IndexStatus.PENDING
    )
    indexed_sha = models.CharField(max_length=64, blank=True)
    last_indexed_at = models.DateTimeField(null=True, blank=True)
    file_count = models.IntegerField(default=0)
    symbol_count = models.IntegerField(default=0)
    edge_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["installation", "full_name"])]

    def __str__(self) -> str:
        return self.full_name

    def effective_settings(self) -> dict[str, Any]:
        """Defaults overlaid with this repository's saved settings."""
        merged = dict(settings.REVIEW_DEFAULTS)
        merged.update(self.settings or {})
        return merged

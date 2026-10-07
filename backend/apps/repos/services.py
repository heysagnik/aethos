"""Installation and repository lifecycle."""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.github import client as github_client
from apps.repos.models import Installation, Repository

logger = logging.getLogger(__name__)


def upsert_installation(
    github_installation_id: int, account_login: str, account_type: str
) -> Installation:
    installation, _ = Installation.objects.update_or_create(
        github_installation_id=github_installation_id,
        defaults={"account_login": account_login, "account_type": account_type},
    )
    return installation


def upsert_repositories(
    installation: Installation, repos: list[dict[str, Any]]
) -> list[Repository]:
    """Create or update repositories from GitHub payloads (`id`, `full_name`, ...)."""
    saved: list[Repository] = []
    with transaction.atomic():
        for item in repos:
            defaults: dict[str, Any] = {
                "installation": installation,
                "full_name": item["full_name"],
                "is_private": bool(item.get("private", False)),
                "removed_at": None,
            }
            if item.get("default_branch"):
                defaults["default_branch"] = item["default_branch"]
            repo, _ = Repository.objects.update_or_create(
                github_repo_id=int(item["id"]), defaults=defaults
            )
            saved.append(repo)
    return saved


def sync_installation_repositories(installation: Installation) -> list[Repository]:
    """Pull the full repository list (with default branches) from GitHub."""
    items = github_client.list_installation_repositories(installation.github_installation_id)
    return upsert_repositories(installation, items)


def try_sync_installation_repositories(installation: Installation) -> None:
    try:
        sync_installation_repositories(installation)
    except Exception:
        logger.exception("Could not sync repositories for installation %s", installation.pk)


def remove_repositories(installation: Installation, github_repo_ids: list[int]) -> int:
    deleted, _ = Repository.objects.filter(
        installation=installation, github_repo_id__in=github_repo_ids
    ).delete()
    return deleted


def delete_installation(github_installation_id: int) -> None:
    Installation.objects.filter(github_installation_id=github_installation_id).delete()


def set_suspended(github_installation_id: int, suspended: bool) -> None:
    Installation.objects.filter(github_installation_id=github_installation_id).update(
        suspended_at=timezone.now() if suspended else None
    )

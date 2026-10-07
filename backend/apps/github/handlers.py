"""Webhook event handlers. Each returns a short outcome string for logging and tests."""

from __future__ import annotations

import re
from typing import Any

from django.conf import settings

from apps.repos import services as repo_services
from apps.repos.models import Installation, Repository
from apps.reviews.queue import enqueue

MAX_INSTRUCTIONS = 500


def parse_command(body: str) -> str | None:
    """Return the instructions after an @mention, or None if the bot is not mentioned."""
    unquoted = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith(">"))
    slug = re.escape(settings.GITHUB_APP_SLUG)
    pattern = re.compile(rf"(?<![\w/@.-])@{slug}(?![\w-])", re.IGNORECASE)
    if not pattern.search(unquoted):
        return None
    return pattern.sub(" ", unquoted).strip()[:MAX_INSTRUCTIONS]


def _is_bot(user: dict[str, Any]) -> bool:
    return user.get("type") == "Bot" or str(user.get("login", "")).endswith("[bot]")


def handle_issue_comment(payload: dict[str, Any]) -> str:
    if payload.get("action") != "created":
        return "ignored: not created"
    issue = payload.get("issue", {})
    if "pull_request" not in issue:
        return "ignored: not a pull request"
    comment = payload.get("comment", {})
    if _is_bot(comment.get("user", {})):
        return "ignored: bot comment"
    instructions = parse_command(comment.get("body", ""))
    if instructions is None:
        return "ignored: no mention"
    repo = Repository.objects.filter(github_repo_id=payload["repository"]["id"]).first()
    if repo is None:
        return "ignored: unknown repository"
    if not repo.effective_settings().get("enabled", True):
        return "ignored: disabled"
    if repo.installation.suspended_at is not None:
        return "ignored: suspended"
    comment_id = int(comment["id"])
    enqueue(
        "triage",
        {
            "repo_id": repo.pk,
            "pr_number": int(issue["number"]),
            "comment_id": comment_id,
            "requested_by": comment.get("user", {}).get("login", ""),
            "instructions": instructions,
        },
        f"triage-{repo.pk}-{comment_id}",
    )
    return "queued"


def _installation_from_payload(payload: dict[str, Any]) -> Installation:
    data = payload["installation"]
    account = data.get("account", {})
    return repo_services.upsert_installation(
        int(data["id"]), account.get("login", ""), account.get("type", "User")
    )


def handle_installation(payload: dict[str, Any]) -> str:
    action = payload.get("action")
    installation_id = int(payload["installation"]["id"])
    if action == "deleted":
        repo_services.delete_installation(installation_id)
        return "installation deleted"
    if action in ("suspend", "unsuspend"):
        repo_services.set_suspended(installation_id, action == "suspend")
        return f"installation {action}"
    if action == "created":
        installation = _installation_from_payload(payload)
        repo_services.upsert_repositories(installation, payload.get("repositories", []))
        repo_services.try_sync_installation_repositories(installation)
        return "installation created"
    return "ignored"


def handle_installation_repositories(payload: dict[str, Any]) -> str:
    installation = _installation_from_payload(payload)
    added = payload.get("repositories_added", [])
    removed = [int(r["id"]) for r in payload.get("repositories_removed", [])]
    if added:
        repo_services.upsert_repositories(installation, added)
        repo_services.try_sync_installation_repositories(installation)
    if removed:
        repo_services.remove_repositories(installation, removed)
    return "repositories updated"


def handle_event(event: str, payload: dict[str, Any]) -> str:
    if event == "issue_comment":
        return handle_issue_comment(payload)
    if event == "installation":
        return handle_installation(payload)
    if event == "installation_repositories":
        return handle_installation_repositories(payload)
    if event == "ping":
        return "pong"
    return "ignored"

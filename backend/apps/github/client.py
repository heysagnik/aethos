"""Thin GitHub REST client plus the gateway used by the review pipeline."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import jwt
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

API_VERSION = "2022-11-28"
TOKEN_CACHE_SECONDS = 50 * 60
FAILING_CONCLUSIONS = {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}
GOOD_CONCLUSIONS = {"success", "neutral", "skipped"}


class GitHubError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"GitHub API error {status}: {message}")
        self.status = status
        self.message = message


@dataclass(frozen=True)
class PullInfo:
    number: int
    title: str
    body: str
    html_url: str
    head_sha: str
    base_sha: str
    draft: bool
    mergeable: bool | None
    author_login: str
    author_type: str
    state: str


class GitHubGateway(Protocol):
    """Everything the review pipeline needs from GitHub (faked in tests)."""

    def get_pull(self, repo: str, number: int) -> PullInfo: ...

    def get_diff(self, repo: str, number: int) -> str: ...

    def get_ci_state(self, repo: str, sha: str) -> str: ...

    def get_file_text(self, repo: str, path: str, ref: str) -> str | None: ...

    def create_review(
        self, repo: str, number: int, head_sha: str, body: str, comments: list[dict[str, Any]]
    ) -> int: ...

    def create_issue_comment(self, repo: str, number: int, body: str) -> int: ...

    def add_reaction(self, repo: str, comment_id: int, content: str) -> None: ...


def app_jwt() -> str:
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": settings.GITHUB_APP_ID}
    return jwt.encode(payload, settings.GITHUB_APP_PRIVATE_KEY, algorithm="RS256")


class GitHubAPI:
    """Minimal authenticated httpx wrapper."""

    def __init__(self, token: str, *, client: httpx.Client | None = None) -> None:
        self._token = token
        self._client = client or httpx.Client(base_url=settings.GITHUB_API_URL, timeout=20.0)

    def request(
        self,
        method: str,
        path: str,
        *,
        accept: str = "application/vnd.github+json",
        ok: tuple[int, ...] = (),
        **kwargs: Any,
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": accept,
            "X-GitHub-Api-Version": API_VERSION,
        }
        response = self._client.request(method, path, headers=headers, **kwargs)
        if response.status_code >= 400 and response.status_code not in ok:
            raise GitHubError(response.status_code, response.text[:300])
        return response

    def json(self, method: str, path: str, **kwargs: Any) -> Any:
        return self.request(method, path, **kwargs).json()

    def paginate(self, path: str, key: str, *, max_pages: int = 10) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            data = self.json("GET", path, params={"per_page": 100, "page": page})
            batch = data.get(key, [])
            items.extend(batch)
            if len(batch) < 100:
                break
        return items


def app_api() -> GitHubAPI:
    return GitHubAPI(app_jwt())


def installation_token(installation_id: int) -> str:
    cache_key = f"gh-install-token:{installation_id}"
    cached = cache.get(cache_key)
    if cached:
        return str(cached)
    data = app_api().json("POST", f"/app/installations/{installation_id}/access_tokens")
    token = str(data["token"])
    cache.set(cache_key, token, TOKEN_CACHE_SECONDS)
    return token


def installation_api(installation_id: int) -> GitHubAPI:
    return GitHubAPI(installation_token(installation_id))


def list_installation_repositories(installation_id: int) -> list[dict[str, Any]]:
    return installation_api(installation_id).paginate("/installation/repositories", "repositories")


def get_installation(installation_id: int) -> dict[str, Any]:
    result: dict[str, Any] = app_api().json("GET", f"/app/installations/{installation_id}")
    return result


class GitHubGatewayImpl:
    def __init__(self, api: GitHubAPI) -> None:
        self._api = api

    def get_pull(self, repo: str, number: int) -> PullInfo:
        data = self._api.json("GET", f"/repos/{repo}/pulls/{number}")
        return PullInfo(
            number=number,
            title=data.get("title") or "",
            body=data.get("body") or "",
            html_url=data["html_url"],
            head_sha=data["head"]["sha"],
            base_sha=data["base"]["sha"],
            draft=bool(data.get("draft")),
            mergeable=data.get("mergeable"),
            author_login=data["user"]["login"],
            author_type=data["user"].get("type", "User"),
            state=data.get("state", "open"),
        )

    def get_diff(self, repo: str, number: int) -> str:
        response = self._api.request(
            "GET", f"/repos/{repo}/pulls/{number}", accept="application/vnd.github.diff"
        )
        return response.text

    def get_ci_state(self, repo: str, sha: str) -> str:
        runs = self._api.json("GET", f"/repos/{repo}/commits/{sha}/check-runs").get(
            "check_runs", []
        )
        combined = self._api.json("GET", f"/repos/{repo}/commits/{sha}/status")
        states: list[str] = []
        for run in runs:
            if run.get("status") != "completed":
                states.append("pending")
            elif run.get("conclusion") in FAILING_CONCLUSIONS:
                states.append("failure")
            elif run.get("conclusion") in GOOD_CONCLUSIONS:
                states.append("success")
        if combined.get("total_count", 0) > 0:
            mapped = {"failure": "failure", "error": "failure", "pending": "pending"}
            states.append(mapped.get(combined.get("state", ""), "success"))
        if not states:
            return "none"
        if "failure" in states:
            return "failure"
        if "pending" in states:
            return "pending"
        return "success"

    def get_file_text(self, repo: str, path: str, ref: str) -> str | None:
        response = self._api.request(
            "GET",
            f"/repos/{repo}/contents/{path}",
            accept="application/vnd.github.raw+json",
            params={"ref": ref},
            ok=(404,),
        )
        return None if response.status_code == 404 else response.text

    def create_review(
        self, repo: str, number: int, head_sha: str, body: str, comments: list[dict[str, Any]]
    ) -> int:
        data = self._api.json(
            "POST",
            f"/repos/{repo}/pulls/{number}/reviews",
            json={"commit_id": head_sha, "body": body, "event": "COMMENT", "comments": comments},
        )
        return int(data["id"])

    def create_issue_comment(self, repo: str, number: int, body: str) -> int:
        data = self._api.json(
            "POST", f"/repos/{repo}/issues/{number}/comments", json={"body": body}
        )
        return int(data["id"])

    def add_reaction(self, repo: str, comment_id: int, content: str) -> None:
        self._api.request(
            "POST",
            f"/repos/{repo}/issues/comments/{comment_id}/reactions",
            json={"content": content},
        )


def get_gateway(installation_id: int) -> GitHubGateway:
    """Factory used by the pipeline. Tests replace this with a fake."""
    return GitHubGatewayImpl(installation_api(installation_id))

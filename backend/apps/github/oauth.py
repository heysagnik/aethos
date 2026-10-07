"""GitHub App user authorization (OAuth) helpers."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from django.conf import settings

from apps.github.client import GitHubAPI, GitHubError

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"  # noqa: S105


@dataclass(frozen=True)
class GitHubUser:
    id: int
    login: str
    avatar_url: str


@dataclass(frozen=True)
class InstallationInfo:
    id: int
    account_login: str
    account_type: str


def authorize_url(state: str) -> str:
    query = urlencode(
        {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": f"{settings.APP_BASE_URL}/api/auth/callback",
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def exchange_code(code: str) -> str:
    response = httpx.post(
        TOKEN_URL,
        headers={"Accept": "application/json"},
        data={
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
        },
        timeout=15.0,
    )
    data = response.json()
    token = data.get("access_token")
    if response.status_code >= 400 or not token:
        raise GitHubError(response.status_code, str(data.get("error", "token exchange failed")))
    return str(token)


def fetch_user(token: str) -> GitHubUser:
    data = GitHubAPI(token).json("GET", "/user")
    return GitHubUser(int(data["id"]), data["login"], data.get("avatar_url", ""))


def fetch_user_installations(token: str) -> list[InstallationInfo]:
    items = GitHubAPI(token).paginate("/user/installations", "installations")
    return [
        InstallationInfo(
            int(item["id"]),
            item["account"]["login"],
            item["account"].get("type", "User"),
        )
        for item in items
    ]

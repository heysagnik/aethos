from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponseRedirect
from django.middleware.csrf import get_token
from ninja import NinjaAPI, Schema
from ninja.security import django_auth

from apps.accounts import services
from apps.github import oauth
from apps.github.client import GitHubError

logger = logging.getLogger(__name__)

api = NinjaAPI(urls_namespace="auth", docs_url=None, openapi_url=None)

STATE_KEY = "oauth_state"
# Set by /api/github/install. With "request user authorization during installation" on, GitHub
# redirects here (the Callback URL) after installing, carrying the install state.
INSTALL_STATE_KEY = "install_state"


class MeOut(Schema):
    login: str
    avatar_url: str
    csrf_token: str
    install_url: str


@api.get("/login", auth=None, url_name="login")
def login_view(request: HttpRequest) -> HttpResponseRedirect:
    state = secrets.token_urlsafe(24)
    request.session[STATE_KEY] = state
    return HttpResponseRedirect(oauth.authorize_url(state))


@api.get("/callback", auth=None, url_name="callback")
def callback(request: HttpRequest, code: str = "", state: str = "") -> HttpResponseRedirect:
    expected = [
        value for key in (STATE_KEY, INSTALL_STATE_KEY) if (value := request.session.pop(key, None))
    ]
    if not code or not any(secrets.compare_digest(value, state) for value in expected):
        return HttpResponseRedirect(f"{settings.FRONTEND_URL}/?error=login_failed")
    try:
        services.complete_login(request, code)
    except GitHubError:
        logger.exception("GitHub login failed")
        return HttpResponseRedirect(f"{settings.FRONTEND_URL}/?error=login_failed")
    return HttpResponseRedirect(f"{settings.FRONTEND_URL}/app")


@api.get("/me", auth=django_auth, response=MeOut, url_name="me")
def me(request: HttpRequest) -> MeOut:
    user = request.user
    return MeOut(
        login=user.get_username(),
        avatar_url=getattr(user, "avatar_url", ""),
        csrf_token=get_token(request),
        install_url=f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new",
    )


@api.post("/logout", auth=django_auth, url_name="logout")
def logout_view(request: HttpRequest) -> dict[str, bool]:
    logout(request)
    return {"ok": True}

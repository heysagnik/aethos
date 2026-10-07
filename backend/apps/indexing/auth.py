"""Authenticate the GitHub Action indexer with its OIDC token (no stored secrets)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import jwt
from django.conf import settings
from django.http import HttpRequest
from ninja.security import HttpBearer

from apps.repos.models import Repository

logger = logging.getLogger(__name__)

ISSUER = "https://token.actions.githubusercontent.com"
JWKS_URL = f"{ISSUER}/.well-known/jwks"

_jwks_client: jwt.PyJWKClient | None = None


class OidcError(Exception):
    """The token is missing, invalid, or not allowed to index this repository."""


@dataclass(frozen=True)
class OidcClaims:
    repository_id: int
    repository: str
    ref: str
    sha: str


def _client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600)
    return _jwks_client


def verify_oidc_token(token: str) -> OidcClaims:
    try:
        key = _client().get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            audience=settings.INDEX_OIDC_AUDIENCE,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
        return OidcClaims(
            repository_id=int(claims["repository_id"]),
            repository=str(claims["repository"]),
            ref=str(claims.get("ref", "")),
            sha=str(claims.get("sha", "")),
        )
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise OidcError(str(exc)) from exc


def authenticate_repository(token: str) -> Repository:
    claims = verify_oidc_token(token)
    repo = Repository.objects.filter(github_repo_id=claims.repository_id).first()
    if repo is None:
        raise OidcError("Repository is not installed")
    if claims.ref != f"refs/heads/{repo.default_branch}":
        raise OidcError("Only the default branch can be indexed")
    return repo


class OidcBearer(HttpBearer):
    def authenticate(self, request: HttpRequest, token: str) -> Repository | None:
        try:
            repo = authenticate_repository(token)
        except OidcError:
            logger.info("Rejected indexer token")
            return None
        request.indexed_repo = repo  # type: ignore[attr-defined]
        return repo

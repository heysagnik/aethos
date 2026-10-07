"""Login: complete the GitHub OAuth flow and link the user to their installations."""

from __future__ import annotations

from django.contrib.auth import login
from django.db import transaction
from django.http import HttpRequest

from apps.accounts.models import User
from apps.github import oauth
from apps.repos import services as repo_services
from apps.repos.models import Installation, InstallationMember


@transaction.atomic
def upsert_user(github_user: oauth.GitHubUser) -> User:
    user, created = User.objects.get_or_create(
        github_user_id=github_user.id,
        defaults={"username": github_user.login, "avatar_url": github_user.avatar_url},
    )
    if created:
        user.set_unusable_password()
    else:
        user.username = github_user.login
        user.avatar_url = github_user.avatar_url
    user.save()
    return user


def link_installations(
    user: User, installations: list[oauth.InstallationInfo]
) -> list[Installation]:
    """Make `user`'s memberships exactly match what GitHub says they can access."""
    linked: list[Installation] = []
    with transaction.atomic():
        for info in installations:
            installation = repo_services.upsert_installation(
                info.id, info.account_login, info.account_type
            )
            InstallationMember.objects.update_or_create(user=user, installation=installation)
            linked.append(installation)
        InstallationMember.objects.filter(user=user).exclude(
            installation__in=[i.pk for i in linked]
        ).delete()
    for installation in linked:
        if not installation.repositories.exists():
            repo_services.try_sync_installation_repositories(installation)
    return linked


def complete_login(request: HttpRequest, code: str) -> User:
    token = oauth.exchange_code(code)
    github_user = oauth.fetch_user(token)
    user = upsert_user(github_user)
    link_installations(user, oauth.fetch_user_installations(token))
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return user

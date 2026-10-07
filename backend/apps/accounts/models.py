from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """A GitHub user. `username` holds the GitHub login; no password is ever set."""

    github_user_id = models.BigIntegerField(unique=True)
    avatar_url = models.URLField(blank=True)

    def __str__(self) -> str:
        return self.username

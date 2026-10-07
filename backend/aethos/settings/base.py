"""Base settings. Everything environment-specific comes from environment variables."""

from __future__ import annotations

import base64
import os
from decimal import Decimal
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_pem(name: str) -> str:
    """Read a PEM from env; accepts raw PEM or base64-encoded PEM."""
    raw = os.environ.get(name, "")
    if not raw or raw.lstrip().startswith("-----BEGIN"):
        return raw.replace("\n", "\n")
    return base64.b64decode(raw).decode()


SECRET_KEY = env("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = [h for h in env("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "apps.accounts",
    "apps.repos",
    "apps.github",
    "apps.indexing",
    "apps.reviews",
    "apps.dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "aethos.urls"
WSGI_APPLICATION = "aethos.wsgi.application"
AUTH_USER_MODEL = "accounts.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
APPEND_SLASH = False

# Serverless: no persistent connections, use Neon's pooled connection string.
DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=0,
        disable_server_side_cursors=True,  # required behind Neon's pooled (pgbouncer) endpoint
    )
}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the SPA reads the token and echoes it in X-CSRFToken

# --- Aethos ---------------------------------------------------------------
APP_BASE_URL = env("APP_BASE_URL", "http://localhost:8000").rstrip("/")
FRONTEND_URL = env("FRONTEND_URL", APP_BASE_URL).rstrip("/")
CSRF_TRUSTED_ORIGINS = [FRONTEND_URL, APP_BASE_URL]

GITHUB_API_URL = "https://api.github.com"
GITHUB_APP_ID = env("GITHUB_APP_ID", "")
GITHUB_APP_SLUG = env("GITHUB_APP_SLUG", "aethos")
GITHUB_APP_PRIVATE_KEY = env_pem("GITHUB_APP_PRIVATE_KEY")
GITHUB_WEBHOOK_SECRET = env("GITHUB_WEBHOOK_SECRET", "")
GITHUB_CLIENT_ID = env("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = env("GITHUB_CLIENT_SECRET", "")

# "qstash" in production; "inline" runs steps synchronously (local dev and tests only).
QUEUE_MODE = env("QUEUE_MODE", "qstash")
QSTASH_URL = env("QSTASH_URL", "")  # regional endpoint, for example https://qstash-us-east-1.upstash.io
QSTASH_TOKEN = env("QSTASH_TOKEN", "")
QSTASH_CURRENT_SIGNING_KEY = env("QSTASH_CURRENT_SIGNING_KEY", "")
QSTASH_NEXT_SIGNING_KEY = env("QSTASH_NEXT_SIGNING_KEY", "")

GROQ_API_KEY = env("GROQ_API_KEY", "")
REVIEW_MODEL = env("REVIEW_MODEL", "llama-3.3-70b-versatile")
LLM_TIMEOUT_SECONDS = float(env("LLM_TIMEOUT_SECONDS", "45"))
LLM_MAX_OUTPUT_TOKENS = int(env("LLM_MAX_OUTPUT_TOKENS", "3000"))
# USD per 1M tokens (input, output). Verify against Groq's pricing page before relying on it.
LLM_PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "llama-3.3-70b-versatile": (Decimal("0.59"), Decimal("0.79")),
    "llama-3.1-8b-instant": (Decimal("0.05"), Decimal("0.08")),
}

# Embeddings: the GitHub Action indexer computes BAAI bge-base-en-v1.5 vectors (768-d) and uploads
# them with each chunk; the server never calls an embedding service. Reviews search with the
# stored vectors of the code being changed. Chunks without a vector use identifier-token matching.
# The dimension is fixed by the model and by the database column.
EMBEDDING_DIM = 768
EMBED_MIN_SIMILARITY = float(env("EMBED_MIN_SIMILARITY", "0.6"))

# Shown in the dashboard's indexing workflow snippet: <owner>/<repo>/<path to action dir>.
INDEXER_ACTION_REPO = env("INDEXER_ACTION_REPO", "OWNER/aethos/action")

# GitHub Actions OIDC token audience the indexer must request.
INDEX_OIDC_AUDIENCE = env("INDEX_OIDC_AUDIENCE", APP_BASE_URL)

# Review defaults (overridable per repository and via .aethos.yml).
REVIEW_DEFAULTS = {
    "enabled": True,
    "mode": "aethos",
    "pack_tokens": 12000,
    "baseline_pack_tokens": 60000,
    "max_comments": 15,
    "min_confidence": 0.5,
    "max_changed_lines": 3000,
    "fan_in_threshold": 5,
    "ignore_paths": [],
    "high_risk_paths": [],
    "block_on": ["critical", "high"],
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}

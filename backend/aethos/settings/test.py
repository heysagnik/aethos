from .base import *  # noqa: F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
QUEUE_MODE = "inline"
GITHUB_APP_ID = "12345"
GITHUB_APP_SLUG = "aethos"
GITHUB_WEBHOOK_SECRET = "test-webhook-secret"
GITHUB_CLIENT_ID = "client-id"
GITHUB_CLIENT_SECRET = "client-secret"
APP_BASE_URL = "http://testserver"
FRONTEND_URL = "http://testserver"
NVIDIA_API_KEY = "test-key"
ALLOWED_HOSTS = ["testserver", "localhost"]

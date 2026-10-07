from .base import *  # noqa: F403

DEBUG = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False  # Vercel terminates TLS
SECURE_HSTS_SECONDS = 31536000

if SECRET_KEY.startswith("insecure"):  # noqa: F405
    raise RuntimeError("DJANGO_SECRET_KEY must be set in production")
if QUEUE_MODE != "qstash":  # noqa: F405
    raise RuntimeError("QUEUE_MODE must be 'qstash' in production")

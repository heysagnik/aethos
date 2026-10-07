"""Vercel entrypoint: exposes the Django WSGI application as `app`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from aethos.wsgi import app  # noqa: F401

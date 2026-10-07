from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.accounts import services as account_services
from apps.github import handlers
from apps.github.client import GitHubError
from apps.github.models import WebhookEvent

logger = logging.getLogger(__name__)

INSTALL_STATE_KEY = "install_state"


def verify_signature(body: bytes, header: str) -> bool:
    if not settings.GITHUB_WEBHOOK_SECRET or not header.startswith("sha256="):
        return False
    expected = hmac.new(settings.GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", header)


@csrf_exempt
@require_POST
def webhook(request: HttpRequest) -> HttpResponse:
    body = request.body
    if not verify_signature(body, request.headers.get("X-Hub-Signature-256", "")):
        return HttpResponse(status=401)
    delivery = request.headers.get("X-GitHub-Delivery", "")
    event = request.headers.get("X-GitHub-Event", "")
    if not delivery or not event:
        return HttpResponse(status=400)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    record, created = WebhookEvent.objects.get_or_create(
        delivery_id=delivery, defaults={"event": event, "action": payload.get("action", "")}
    )
    if not created and record.processed_at is not None:
        return JsonResponse({"status": "duplicate"})

    outcome = handlers.handle_event(event, payload)
    record.processed_at = timezone.now()
    record.save(update_fields=["processed_at"])
    logger.info("webhook %s %s -> %s", event, payload.get("action", ""), outcome)
    return JsonResponse({"status": outcome}, status=202)


@require_GET
def install_redirect(request: HttpRequest) -> HttpResponse:
    """Landing-page Install button: send the user to GitHub's repository picker."""
    state = secrets.token_urlsafe(24)
    request.session[INSTALL_STATE_KEY] = state
    url = f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new?state={state}"
    return HttpResponseRedirect(url)


@require_GET
def setup_callback(request: HttpRequest) -> HttpResponse:
    """GitHub redirects here after installation (Setup URL)."""
    expected = request.session.pop(INSTALL_STATE_KEY, None)
    state = request.GET.get("state", "")
    code = request.GET.get("code", "")
    if not expected or not state or not secrets.compare_digest(expected, state) or not code:
        # Installed from GitHub directly (or the state expired): go through plain login.
        return HttpResponseRedirect("/api/auth/login")
    try:
        account_services.complete_login(request, code)
    except GitHubError:
        logger.exception("Post-install login failed")
        return HttpResponseRedirect(f"{settings.FRONTEND_URL}/?error=install_failed")
    return HttpResponseRedirect(f"{settings.FRONTEND_URL}/app")

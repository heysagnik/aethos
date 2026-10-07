"""QStash-delivered pipeline steps."""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from qstash import Receiver
from qstash.errors import SignatureError

from apps.reviews import pipeline
from apps.reviews.queue import STEP_RETRIES

logger = logging.getLogger(__name__)


def _verify(request: HttpRequest) -> bool:
    receiver = Receiver(
        current_signing_key=settings.QSTASH_CURRENT_SIGNING_KEY,
        next_signing_key=settings.QSTASH_NEXT_SIGNING_KEY,
    )
    try:
        receiver.verify(
            signature=request.headers.get("Upstash-Signature", ""),
            body=request.body.decode(),
            url=f"{settings.APP_BASE_URL}{request.path}",
        )
    except SignatureError:
        return False
    return True


@csrf_exempt
@require_POST
def run_step(request: HttpRequest, step: str) -> HttpResponse:
    if settings.QUEUE_MODE != "qstash":
        return HttpResponse(status=404)
    if step not in pipeline.STEPS:
        return HttpResponse(status=404)
    if not _verify(request):
        return HttpResponse(status=401)
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    try:
        pipeline.run_step(step, payload)
    except Exception as exc:
        retried = int(request.headers.get("Upstash-Retried", "0") or 0)
        logger.exception("Step %s failed (attempt %s)", step, retried + 1)
        if retried >= STEP_RETRIES:
            pipeline.mark_failed(step, payload, f"{type(exc).__name__}: {exc}")
            return JsonResponse({"status": "failed"})
        return HttpResponse(status=500)
    return JsonResponse({"status": "ok"})

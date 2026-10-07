from __future__ import annotations

from django.db import models


class WebhookEvent(models.Model):
    """One row per GitHub delivery; the primary key is the dedupe key."""

    delivery_id = models.CharField(max_length=64, primary_key=True)
    event = models.CharField(max_length=64)
    action = models.CharField(max_length=64, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.event}.{self.action} {self.delivery_id}"

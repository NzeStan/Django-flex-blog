"""Infrastructure models: notifications, webhooks, idempotency and delivery receipts."""

import secrets

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from flex_blog.models.base import BaseModel


class Notification(BaseModel):
    """In-app notification for a user (the "bell" in your UI)."""

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blog_notifications")
    event = models.CharField(_("event"), max_length=100, db_index=True)
    title = models.CharField(_("title"), max_length=255)
    body = models.TextField(_("body"), blank=True)
    url = models.CharField(_("URL"), max_length=500, blank=True)
    data = models.JSONField(_("data"), default=dict, blank=True)
    is_read = models.BooleanField(_("read"), default=False)
    read_at = models.DateTimeField(_("read at"), null=True, blank=True)
    # Same logical notification is never stored twice (task retries, double signals).
    dedupe_key = models.CharField(_("dedupe key"), max_length=255, unique=True, null=True, blank=True, editable=False)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read", "-created_at"], name="flexblog_notif_inbox")]

    def __str__(self):
        return self.title


def _webhook_secret():
    return secrets.token_hex(32)


class WebhookEndpoint(BaseModel):
    """An external URL that receives signed JSON for selected events."""

    name = models.CharField(_("name"), max_length=100)
    url = models.URLField(_("URL"), max_length=500)
    secret = models.CharField(_("signing secret"), max_length=128, default=_webhook_secret)
    events = models.JSONField(_("events"), default=list, blank=True, help_text=_('Event names, or ["*"] for all events.'))
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("webhook endpoint")
        verbose_name_plural = _("webhook endpoints")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def accepts(self, event):
        return self.is_active and ("*" in (self.events or []) or event in (self.events or []))

    def clean(self):
        from flex_blog.webhooks import validate_webhook_url

        validate_webhook_url(self.url)


class WebhookDelivery(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        SUCCESS = "success", _("Delivered")
        FAILED = "failed", _("Failed")

    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name="deliveries")
    event = models.CharField(_("event"), max_length=100)
    event_id = models.UUIDField(_("event id"))
    payload = models.JSONField(_("payload"), default=dict)
    status = models.CharField(_("status"), max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(_("attempts"), default=0)
    response_status = models.PositiveSmallIntegerField(_("response status"), null=True, blank=True)
    last_error = models.TextField(_("last error"), blank=True)
    delivered_at = models.DateTimeField(_("delivered at"), null=True, blank=True)

    class Meta:
        verbose_name = _("webhook delivery")
        verbose_name_plural = _("webhook deliveries")
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["endpoint", "event_id"], name="flexblog_unique_webhook_delivery")]

    def __str__(self):
        return f"{self.event} → {self.endpoint}"


class IdempotencyRecord(BaseModel):
    """Stored response for an ``Idempotency-Key`` so a retried request replays it."""

    class Status(models.TextChoices):
        PROCESSING = "processing", _("Processing")
        COMPLETED = "completed", _("Completed")

    scope = models.CharField(max_length=150)
    key = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=500)
    fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROCESSING)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = _("idempotency record")
        verbose_name_plural = _("idempotency records")
        constraints = [models.UniqueConstraint(fields=["scope", "key"], name="flexblog_unique_idempotency_key")]

    def __str__(self):
        return f"{self.method} {self.path} [{self.key}]"


class DeliveryReceipt(models.Model):
    """
    "This message was already sent" marker. Inserting the key is the lock: if
    the insert fails, someone else already sent it, so retries never double-send.
    """

    key = models.CharField(max_length=255, primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("delivery receipt")
        verbose_name_plural = _("delivery receipts")

    def __str__(self):
        return self.key

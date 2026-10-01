"""Periodic housekeeping. Safe to run as often as you like, from many workers at once."""

from datetime import timedelta

from django.utils import timezone

from flex_blog.conf import blog_settings
from flex_blog.models import DeliveryReceipt, IdempotencyRecord, Subscriber


def purge_idempotency_records():
    cutoff = timezone.now() - timedelta(seconds=blog_settings.IDEMPOTENCY["ttl_seconds"])
    return IdempotencyRecord.objects.filter(created_at__lt=cutoff).delete()[0]


def purge_receipts(days=90):
    return DeliveryReceipt.objects.filter(created_at__lt=timezone.now() - timedelta(days=days)).delete()[0]


def purge_unconfirmed_subscribers(days=30):
    cutoff = timezone.now() - timedelta(days=days)
    return Subscriber.objects.filter(status=Subscriber.Status.PENDING, created_at__lt=cutoff).delete()[0]


def run_all():
    from flex_blog.services import articles

    result = {"announced": articles.announce_due()}
    if blog_settings.feature_enabled("webhooks"):
        from flex_blog import webhooks

        result["webhooks_retried"] = webhooks.retry_failed()
    result["idempotency_purged"] = purge_idempotency_records()
    result["receipts_purged"] = purge_receipts()
    if blog_settings.feature_enabled("newsletter"):
        result["subscribers_purged"] = purge_unconfirmed_subscribers()
    return result

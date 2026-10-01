"""Exactly-once guards for outgoing messages (emails, notifications)."""

import hashlib

from django.db import IntegrityError, transaction

from flex_blog.models import DeliveryReceipt


def _normalise(key):
    key = str(key)
    if len(key) > 255:
        key = key[:190] + ":" + hashlib.sha256(key.encode()).hexdigest()
    return key


def claim(key):
    """Return True if this caller is the first to claim ``key``."""
    try:
        with transaction.atomic():
            DeliveryReceipt.objects.create(key=_normalise(key))
        return True
    except IntegrityError:
        return False


def release(key):
    """Give the claim back (call when sending failed so a retry may send)."""
    DeliveryReceipt.objects.filter(key=_normalise(key)).delete()

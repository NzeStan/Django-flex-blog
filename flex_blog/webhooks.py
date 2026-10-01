"""
Outgoing webhooks.

Each domain event becomes one ``WebhookDelivery`` per subscribed endpoint
(unique per endpoint + event id, so an event is never queued twice). The
request body is JSON::

    {"id": "<event uuid>", "event": "article_published", "created_at": "...", "data": {...}}

Headers let the receiver verify and de-duplicate:

* ``X-FlexBlog-Event``: event name
* ``X-FlexBlog-Delivery``: event id, the same on every retry (your idempotency key)
* ``X-FlexBlog-Signature``: ``t=<unix ts>,v1=<hex HMAC-SHA256(secret, "<t>.<body>")>``

Verify with ``flex_blog.webhooks.verify_signature(secret, body, header)``.
"""

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import time
import urllib.error
import urllib.request
from datetime import timedelta
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django.utils.translation import gettext as _

from flex_blog.conf import blog_settings

logger = logging.getLogger("flex_blog")

USER_AGENT = "django-flex-blog-webhooks/1"


class WebhookError(Exception):
    pass


def _is_private_host(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return True
    return False


def validate_webhook_url(url):
    """Block plain http and internal addresses (SSRF) unless explicitly allowed."""
    conf = blog_settings.WEBHOOKS
    parsed = urlparse(url or "")
    allowed = {"https", "http"} if conf["allow_http"] else {"https"}
    if parsed.scheme not in allowed or not parsed.hostname:
        raise ValidationError(_("Webhook URLs must use https."))
    if not conf["allow_private_hosts"] and _is_private_host(parsed.hostname):
        raise ValidationError(_("Webhook URLs may not point to private or local addresses."))


def sign(secret, body, timestamp=None):
    timestamp = int(timestamp or time.time())
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def verify_signature(secret, body, header, tolerance=300):
    """Helper for *receivers* of flex_blog webhooks."""
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs(time.time() - timestamp) > tolerance:
        return False
    expected = sign(secret, body, timestamp).split("v1=")[1]
    return hmac.compare_digest(expected, parts.get("v1", ""))


# --- payloads ----------------------------------------------------------------


def _article(article):
    from flex_blog.urls_utils import frontend_url

    return {
        "id": str(article.pk), "slug": article.slug, "title": article.title,
        "excerpt": article.excerpt, "url": frontend_url("article", absolute=True, slug=article.slug),
        "status": article.status, "visibility": article.visibility, "published_at": article.published_at,
        "author": article.author.display_name if article.author_id else None,
    }


def serialize_payload(payload):
    data = {}
    for key, value in payload.items():
        name = type(value).__name__
        if name == "Article":
            data[key] = _article(value)
        elif name == "Comment":
            data[key] = {
                "id": str(value.pk), "article": _article(value.article), "status": value.status,
                "author_name": str(value.display_name), "parent": str(value.parent_id) if value.parent_id else None,
                "content": value.content[:1000],
            }
        elif name == "Reaction":
            data[key] = {"id": str(value.pk), "article": _article(value.article), "kind": value.kind, "user": str(value.user_id)}
        elif name == "Bookmark":
            data[key] = {"article": _article(value.article), "user": str(value.user_id)}
        elif name == "Subscriber":
            data[key] = {"id": str(value.pk), "email": value.email, "status": value.status}
        elif hasattr(value, "pk"):
            data[key] = str(value.pk)
        else:
            data[key] = value
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def dispatch(event, event_id, payload):
    """Create deliveries for every endpoint subscribed to ``event`` and queue them."""
    from flex_blog.models import WebhookDelivery, WebhookEndpoint
    from flex_blog.tasks import deliver_webhook, enqueue

    endpoints = [e for e in WebhookEndpoint.objects.filter(is_active=True) if e.accepts(event)]
    if not endpoints:
        return 0
    body = {"id": str(event_id), "event": event, "created_at": timezone.now().isoformat(), "data": serialize_payload(payload)}
    queued = 0
    for endpoint in endpoints:
        delivery, created = WebhookDelivery.objects.get_or_create(
            endpoint=endpoint, event_id=event_id, defaults={"event": event, "payload": body},
        )
        if created:
            enqueue(deliver_webhook, str(delivery.pk))
            queued += 1
    return queued


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # Following redirects would let an endpoint bounce us to internal hosts.
    def redirect_request(self, *args, **kwargs):
        return None


def deliver(delivery_id, raise_on_failure=False):
    """POST one delivery. Already-delivered deliveries are skipped (idempotent)."""
    from flex_blog.models import WebhookDelivery

    delivery = WebhookDelivery.objects.select_related("endpoint").filter(pk=delivery_id).first()
    if delivery is None or delivery.status == WebhookDelivery.Status.SUCCESS:
        return True
    endpoint = delivery.endpoint
    body = json.dumps(delivery.payload, cls=DjangoJSONEncoder).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-FlexBlog-Event": delivery.event,
        "X-FlexBlog-Delivery": str(delivery.event_id),
        "X-FlexBlog-Signature": sign(endpoint.secret, body),
    }
    error, status = "", None
    try:
        validate_webhook_url(endpoint.url)  # re-checked at send time (DNS may have changed)
        request = urllib.request.Request(endpoint.url, data=body, headers=headers, method="POST")
        opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(request, timeout=blog_settings.WEBHOOKS["timeout"]) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        status, error = exc.code, f"HTTP {exc.code}"
    except Exception as exc:  # network errors, timeouts, validation
        error = str(exc)[:1000] or exc.__class__.__name__

    delivery.attempts += 1
    delivery.response_status = status
    if status is not None and 200 <= status < 300:
        delivery.status = WebhookDelivery.Status.SUCCESS
        delivery.delivered_at = timezone.now()
        delivery.last_error = ""
    else:
        delivery.status = WebhookDelivery.Status.FAILED
        delivery.last_error = error or f"HTTP {status}"
    delivery.save(update_fields=["attempts", "response_status", "status", "delivered_at", "last_error", "updated_at"])
    if delivery.status == WebhookDelivery.Status.FAILED:
        logger.warning("flex_blog: webhook %s to %s failed: %s", delivery.event, endpoint.url, delivery.last_error)
        if raise_on_failure:
            raise WebhookError(delivery.last_error)
        return False
    return True


def retry_failed():
    """Retry failed deliveries with exponential backoff (1, 2, 4 ... minutes)."""
    from flex_blog.models import WebhookDelivery
    from flex_blog.tasks import deliver_webhook, enqueue

    now = timezone.now()
    retried = 0
    pending = WebhookDelivery.objects.filter(
        status=WebhookDelivery.Status.FAILED,
        attempts__lt=blog_settings.WEBHOOKS["max_retries"],
        endpoint__is_active=True,
    ).only("pk", "attempts", "updated_at")[:500]
    for delivery in pending:
        if delivery.updated_at <= now - timedelta(minutes=2 ** max(delivery.attempts - 1, 0)):
            enqueue(deliver_webhook, str(delivery.pk))
            retried += 1
    return retried

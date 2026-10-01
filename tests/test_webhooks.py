import json
from datetime import timedelta

import pytest
from django.utils import timezone

from flex_blog import webhooks
from flex_blog.models import Article, WebhookDelivery, WebhookEndpoint

from .conftest import make_article

pytestmark = pytest.mark.django_db


class FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def endpoint(settings):
    # Public-looking URL; DNS lookups are stubbed below.
    return WebhookEndpoint.objects.create(name="Zapier", url="https://hooks.example.com/in", events=["article_published"])


class Calls(list):
    opener = None


@pytest.fixture
def sent(monkeypatch):
    calls = Calls()

    class Opener:
        def __init__(self, status=200):
            self.status = status

        def open(self, request, timeout=None):
            calls.append(request)
            return FakeResponse(Opener.next_status)

    Opener.next_status = 200
    monkeypatch.setattr(webhooks.urllib.request, "build_opener", lambda *a: Opener())
    monkeypatch.setattr(webhooks, "_is_private_host", lambda host: False)
    calls.opener = Opener
    return calls


def test_published_event_delivered_and_signed(endpoint, sent, author):
    article = make_article(author, title="Webhook me")
    delivery = WebhookDelivery.objects.get()
    assert delivery.status == WebhookDelivery.Status.SUCCESS and delivery.attempts == 1
    request = sent[0]
    body = request.data
    payload = json.loads(body)
    assert payload["event"] == "article_published"
    assert payload["data"]["article"]["slug"] == article.slug
    assert payload["data"]["article"]["url"] == "https://blog.example.com/blog/webhook-me/"
    headers = {k.lower(): v for k, v in request.header_items()}
    assert headers["x-flexblog-delivery"] == payload["id"]
    assert webhooks.verify_signature(endpoint.secret, body, headers["x-flexblog-signature"])
    assert not webhooks.verify_signature("wrong", body, headers["x-flexblog-signature"])
    assert not webhooks.verify_signature(endpoint.secret, body, "garbage")


def test_unsubscribed_events_ignored(endpoint, sent, reader, article):
    from flex_blog.services import engagement

    engagement.add_reaction(article, reader)
    assert WebhookDelivery.objects.filter(event="reaction_added").count() == 0


def test_wildcard_endpoint(sent, reader, article):
    WebhookEndpoint.objects.create(name="All", url="https://all.example.com/", events=["*"])
    from flex_blog.services import engagement

    engagement.add_reaction(article, reader)
    assert WebhookDelivery.objects.filter(event="reaction_added").count() == 1


def test_failed_delivery_retried_with_backoff(endpoint, sent, author):
    sent.opener.next_status = 500
    make_article(author)
    delivery = WebhookDelivery.objects.get()
    assert delivery.status == WebhookDelivery.Status.FAILED and delivery.last_error
    assert webhooks.retry_failed() == 0  # backoff not elapsed
    WebhookDelivery.objects.filter(pk=delivery.pk).update(updated_at=timezone.now() - timedelta(minutes=5))
    sent.opener.next_status = 204
    assert webhooks.retry_failed() == 1
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.Status.SUCCESS and delivery.attempts == 2
    # Delivering again is a no-op.
    assert webhooks.deliver(delivery.pk) is True
    assert len(sent) == 2


def test_network_error_recorded(endpoint, monkeypatch, author):
    class Boom:
        def open(self, *a, **k):
            raise OSError("connection refused")

    monkeypatch.setattr(webhooks.urllib.request, "build_opener", lambda *a: Boom())
    monkeypatch.setattr(webhooks, "_is_private_host", lambda host: False)
    make_article(author)
    assert "connection refused" in WebhookDelivery.objects.get().last_error


def test_private_target_blocked_at_send_time(endpoint, author):
    WebhookEndpoint.objects.filter(pk=endpoint.pk).update(url="https://127.0.0.1/x")
    make_article(author)
    delivery = WebhookDelivery.objects.get()
    assert delivery.status == WebhookDelivery.Status.FAILED


def test_same_event_never_queued_twice(endpoint, sent, author):
    article = make_article(author, status=Article.Status.DRAFT)
    event_id = "11111111-1111-1111-1111-111111111111"
    webhooks.dispatch("article_published", event_id, {"article": article})
    webhooks.dispatch("article_published", event_id, {"article": article})
    assert WebhookDelivery.objects.count() == 1


def test_webhooks_feature_off(settings, endpoint, sent, author):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "FEATURES": {"webhooks": False}}
    make_article(author)
    assert not WebhookDelivery.objects.exists()


def test_endpoint_clean_validates_url(settings):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        WebhookEndpoint(name="bad", url="http://insecure.example.com").full_clean()

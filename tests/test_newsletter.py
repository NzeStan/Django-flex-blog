import re
from urllib.parse import unquote

import pytest
from django.core import mail

from flex_blog.models import Article, Subscriber
from flex_blog.services import articles as article_service
from flex_blog.services import newsletter

from .conftest import API, client_for, make_article

pytestmark = pytest.mark.django_db


def confirm_token():
    body = mail.outbox[-1].body
    return unquote(re.search(r"token=([^\s]+)", body).group(1))


def subscribe(client, email="ada@example.com"):
    return client.post(f"{API}/newsletter/subscribe/", {"email": email, "name": "Ada"})


def test_double_opt_in_flow(anon):
    response = subscribe(anon)
    assert response.status_code == 202
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["ada@example.com"]
    assert "https://blog.example.com/newsletter/confirm/?token=" in mail.outbox[0].body
    # Repeating the request is idempotent and sends nothing new.
    assert subscribe(anon, "ADA@example.com").status_code == 202
    assert len(mail.outbox) == 1
    token = confirm_token()
    assert anon.post(f"{API}/newsletter/confirm/", {"token": token}).status_code == 200
    assert anon.post(f"{API}/newsletter/confirm/", {"token": token}).status_code == 200
    assert Subscriber.objects.get().status == Subscriber.Status.CONFIRMED
    assert anon.post(f"{API}/newsletter/confirm/", {"token": "bad"}).status_code == 400


def test_unsubscribe_and_resubscribe(settings, anon):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "THROTTLE_RATES": {"newsletter": "100/min"}}
    subscribe(anon)
    anon.post(f"{API}/newsletter/confirm/", {"token": confirm_token()})
    subscriber = Subscriber.objects.get()
    old_token = subscriber.token
    assert anon.post(f"{API}/newsletter/unsubscribe/", {"token": old_token}).status_code == 200
    assert anon.post(f"{API}/newsletter/unsubscribe/", {"token": old_token}).status_code == 200
    assert anon.post(f"{API}/newsletter/unsubscribe/", {"token": "guess"}).status_code == 400
    subscribe(anon)
    subscriber.refresh_from_db()
    assert subscriber.status == Subscriber.Status.PENDING and subscriber.token != old_token
    assert len(mail.outbox) == 2


def test_same_answer_for_known_and_unknown_emails(anon):
    first = subscribe(anon, "one@example.com").data
    second = subscribe(anon, "one@example.com").data
    assert first == second
    assert subscribe(anon, "not-an-email").status_code == 400


def test_single_opt_in(settings, anon):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "NEWSLETTER": {"double_opt_in": False}}
    subscribe(anon)
    assert Subscriber.objects.get().status == Subscriber.Status.CONFIRMED
    assert len(mail.outbox) == 0


def test_new_article_sent_once_to_confirmed(settings, author):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "NEWSLETTER": {"batch_size": 2}}
    for i in range(3):
        Subscriber.objects.create(email=f"s{i}@example.com", status=Subscriber.Status.CONFIRMED)
    Subscriber.objects.create(email="pending@example.com")
    Subscriber.objects.create(email="gone@example.com", status=Subscriber.Status.UNSUBSCRIBED)
    article = make_article(author, title="Big news", status=Article.Status.DRAFT)
    article_service.publish(article)
    assert sorted(m.to[0] for m in mail.outbox) == ["s0@example.com", "s1@example.com", "s2@example.com"]
    message = mail.outbox[0]
    assert message.subject == "Big news"
    assert "https://blog.example.com/blog/big-news/" in message.body
    assert message.extra_headers["List-Unsubscribe"].startswith("<https://blog.example.com/newsletter/unsubscribe/")
    # Retries/duplicate jobs never re-send.
    newsletter.fan_out(str(article.pk))
    newsletter.send_batch(str(article.pk), [str(s.pk) for s in Subscriber.objects.all()])
    assert len(mail.outbox) == 3


def test_unlisted_and_disabled_do_not_send(settings, author):
    Subscriber.objects.create(email="s@example.com", status=Subscriber.Status.CONFIRMED)
    make_article(author, title="Quiet", visibility=Article.Visibility.UNLISTED)
    assert len(mail.outbox) == 0
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "NEWSLETTER": {"send_on_publish": False}}
    make_article(author, title="Also quiet")
    assert len(mail.outbox) == 0


def test_feature_disabled(settings, anon):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "FEATURES": {"newsletter": False}}
    assert subscribe(anon).status_code == 404


def test_logged_in_users_can_subscribe(reader):
    assert subscribe(client_for(reader)).status_code == 202


def test_newsletter_is_throttled(anon):
    codes = [subscribe(anon, f"u{i}@example.com").status_code for i in range(6)]
    assert codes[-1] == 429

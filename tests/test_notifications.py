import pytest
from django.core import mail

from flex_blog.models import Comment, DeliveryReceipt, Notification
from flex_blog.notifications import NotificationMessage, deliver, notify

from .conftest import API, client_for, make_user

pytestmark = pytest.mark.django_db


def comment(client, article, **data):
    data.setdefault("content", "Nice article!")
    return client.post(f"{API}/articles/{article.slug}/comments/", data).data


def test_author_notified_of_new_comment(moderator, article):
    comment(client_for(moderator), article)
    notification = Notification.objects.get(recipient=article.author.user)
    assert notification.event == "comment_on_article"
    assert notification.url.startswith(f"/blog/{article.slug}/#comment-")
    assert [m.to for m in mail.outbox] == [[article.author.user.email]]


def test_reply_notifies_parent_author_once(moderator, article):
    parent_user = make_user("parent")
    Comment.objects.create(article=article, user=parent_user, content="first!", status="approved")
    parent = Comment.objects.get()
    comment(client_for(moderator), article, parent=str(parent.pk))
    assert Notification.objects.filter(recipient=parent_user, event="comment_reply").count() == 1
    assert Notification.objects.filter(recipient=article.author.user).count() == 1


def test_no_self_notification(article):
    comment(client_for(article.author.user), article)
    Comment.objects.update(status="approved")
    assert not Notification.objects.filter(recipient=article.author.user).exists()


def test_commenter_told_when_approved(reader, moderator, article):
    comment_id = comment(client_for(reader), article)["id"]
    assert not Notification.objects.filter(recipient=reader).exists()
    client_for(moderator).post(f"{API}/comments/{comment_id}/approve/")
    assert Notification.objects.filter(recipient=reader, event="comment_approved").count() == 1


def test_moderators_emailed_for_pending(settings, reader, article):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "NOTIFICATIONS": {"moderator_emails": ["mods@example.com"]}}
    comment(client_for(reader), article)
    assert ["mods@example.com"] in [m.to for m in mail.outbox]


def test_dedupe_key_prevents_duplicates(reader):
    message = NotificationMessage(event="x", title="Hi", recipient_id=str(reader.pk), dedupe_key="same")
    deliver(message.to_dict())
    deliver(message.to_dict())
    assert Notification.objects.count() == 1
    assert len(mail.outbox) == 1
    assert DeliveryReceipt.objects.count() == 2  # one per backend


def test_recipient_filter_and_feature_flag(settings, reader):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "NOTIFICATIONS": {"recipient_filter": "tests.hooks.keep_comment_reply_only"}}
    assert notify(NotificationMessage(event="other", title="t", recipient_id=str(reader.pk))) is False
    assert notify(NotificationMessage(event="comment_reply", title="t", recipient_id=str(reader.pk))) is True
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "FEATURES": {"notifications": False}}
    assert notify(NotificationMessage(event="comment_reply", title="t", recipient_id=str(reader.pk))) is False


def test_custom_backend(settings, reader):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "NOTIFICATIONS": {"backends": ["flex_blog.notifications.backends.LoggingBackend"]}}
    notify(NotificationMessage(event="e", title="t", recipient_id=str(reader.pk)))
    assert not Notification.objects.exists()


def test_failing_backend_releases_claim(settings, reader, monkeypatch):
    from flex_blog.notifications import backends

    monkeypatch.setattr(backends.EmailBackend, "send", lambda self, m: (_ for _ in ()).throw(RuntimeError("smtp down")))
    message = NotificationMessage(event="e", title="t", recipient_id=str(reader.pk), dedupe_key="k1")
    deliver(message.to_dict())
    assert not DeliveryReceipt.objects.filter(key="notify:email:k1").exists()
    assert DeliveryReceipt.objects.filter(key="notify:in_app:k1").exists()


def test_inbox_endpoints(reader):
    for i in range(3):
        Notification.objects.create(recipient=reader, event="e", title=f"n{i}")
    Notification.objects.create(recipient=make_user("other"), event="e", title="not yours")
    client = client_for(reader)
    assert client.get(f"{API}/notifications/").data["count"] == 3
    assert client.get(f"{API}/notifications/unread-count/").data == {"count": 3}
    first = Notification.objects.filter(recipient=reader).first()
    assert client.post(f"{API}/notifications/{first.pk}/read/").data["is_read"] is True
    assert client.get(f"{API}/notifications/?unread=true").data["count"] == 2
    assert client.post(f"{API}/notifications/read-all/").data == {"updated": 2}
    assert client.delete(f"{API}/notifications/{first.pk}/").status_code == 204
    foreign = Notification.objects.get(title="not yours")
    assert client.get(f"{API}/notifications/{foreign.pk}/").status_code == 404

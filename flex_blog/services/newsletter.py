import logging

from django.core import signing
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _

from flex_blog import receipts
from flex_blog.conf import blog_settings
from flex_blog.models import Article, Subscriber
from flex_blog.models.engagement import _subscriber_token
from flex_blog.signals import emit
from flex_blog.urls_utils import frontend_url

logger = logging.getLogger("flex_blog")

CONFIRM_SALT = "flex_blog.newsletter.confirm"


def _from_email():
    from django.conf import settings

    return blog_settings.NEWSLETTER["from_email"] or settings.DEFAULT_FROM_EMAIL


def _mail_connection():
    """One reusable SMTP connection (Django 6.1+ ``mailers``, older ``get_connection``)."""
    try:
        from django.core.mail import mailers
    except ImportError:  # Django < 6.1
        from django.core.mail import get_connection

        return get_connection()
    return mailers.default


def subscribe(email, name="", language="", source=""):
    """
    Idempotent and enumeration safe: callers always get the same answer, so
    nobody can probe who is subscribed. Only state changes send email.
    """
    from django.core.validators import validate_email

    email = (email or "").strip().lower()
    validate_email(email)
    double_opt_in = blog_settings.NEWSLETTER["double_opt_in"]
    initial = Subscriber.Status.PENDING if double_opt_in else Subscriber.Status.CONFIRMED
    try:
        with transaction.atomic():
            subscriber, created = Subscriber.objects.select_for_update().get_or_create(
                email=email,
                defaults={
                    "name": name[:150], "language": language[:15], "source": source[:100], "status": initial,
                    "confirmed_at": None if double_opt_in else timezone.now(),
                },
            )
            if not created and subscriber.status == Subscriber.Status.UNSUBSCRIBED:
                subscriber.status = initial
                subscriber.token = _subscriber_token()
                subscriber.unsubscribed_at = None
                subscriber.confirmed_at = None if double_opt_in else timezone.now()
                subscriber.save()
                created = True
    except IntegrityError:  # a concurrent request created it first
        return Subscriber.objects.get(email=email)
    if created and subscriber.status == Subscriber.Status.PENDING:
        from flex_blog.tasks import enqueue, send_subscription_confirmation

        enqueue(send_subscription_confirmation, str(subscriber.pk))
    elif created:
        emit("subscriber_confirmed", sender=Subscriber, subscriber=subscriber)
    return subscriber


def make_confirm_token(subscriber):
    return signing.dumps({"s": str(subscriber.pk), "e": subscriber.email}, salt=CONFIRM_SALT, compress=True)


def send_confirmation(subscriber_id):
    subscriber = Subscriber.objects.filter(pk=subscriber_id, status=Subscriber.Status.PENDING).first()
    if subscriber is None:
        return False
    context = {
        "subscriber": subscriber,
        "site_name": blog_settings.SITE_NAME,
        "confirm_url": frontend_url("newsletter_confirm", absolute=True, token=make_confirm_token(subscriber)),
    }
    subject = " ".join(render_to_string("flex_blog/email/newsletter_confirm_subject.txt", context).split())
    body = render_to_string("flex_blog/email/newsletter_confirm.txt", context)
    EmailMultiAlternatives(subject, body, _from_email(), [subscriber.email]).send()
    return True


def confirm(token):
    """Idempotent: confirming twice returns the same subscriber."""
    try:
        data = signing.loads(token, salt=CONFIRM_SALT, max_age=blog_settings.NEWSLETTER["confirm_max_age"])
    except signing.BadSignature:
        raise ValidationError({"token": _("This confirmation link is invalid or has expired.")})
    with transaction.atomic():
        subscriber = Subscriber.objects.select_for_update().filter(pk=data.get("s"), email=data.get("e")).first()
        if subscriber is None:
            raise ValidationError({"token": _("This confirmation link is invalid or has expired.")})
        if subscriber.status == Subscriber.Status.CONFIRMED:
            return subscriber
        subscriber.status = Subscriber.Status.CONFIRMED
        subscriber.confirmed_at = timezone.now()
        subscriber.unsubscribed_at = None
        subscriber.save()
    emit("subscriber_confirmed", sender=Subscriber, subscriber=subscriber)
    return subscriber


def unsubscribe(token):
    """Idempotent. Unknown tokens are rejected so links can't be guessed."""
    with transaction.atomic():
        subscriber = Subscriber.objects.select_for_update().filter(token=token).first() if token else None
        if subscriber is None:
            raise ValidationError({"token": _("This unsubscribe link is invalid.")})
        if subscriber.status == Subscriber.Status.UNSUBSCRIBED:
            return subscriber
        subscriber.status = Subscriber.Status.UNSUBSCRIBED
        subscriber.unsubscribed_at = timezone.now()
        subscriber.save()
    emit("subscriber_unsubscribed", sender=Subscriber, subscriber=subscriber)
    return subscriber


def fan_out(article_id):
    """Split the subscriber list into batches and queue one job per batch."""
    from flex_blog.tasks import enqueue, send_newsletter_batch

    article = Article.objects.filter(pk=article_id).first()
    if article is None or not article.is_live or article.visibility == Article.Visibility.UNLISTED:
        return 0
    if not receipts.claim(f"newsletter-fanout:{article_id}"):
        return 0
    size = max(int(blog_settings.NEWSLETTER["batch_size"]), 1)
    ids = Subscriber.objects.filter(status=Subscriber.Status.CONFIRMED).order_by("pk").values_list("pk", flat=True)
    batches, batch = 0, []
    for pk in ids.iterator(chunk_size=2000):
        batch.append(str(pk))
        if len(batch) >= size:
            enqueue(send_newsletter_batch, str(article_id), batch)
            batches, batch = batches + 1, []
    if batch:
        enqueue(send_newsletter_batch, str(article_id), batch)
        batches += 1
    return batches


def send_batch(article_id, subscriber_ids):
    """Send one batch over one SMTP connection. Each recipient gets it once."""
    article = Article.objects.with_relations().filter(pk=article_id).first()
    if article is None or not article.is_live:
        return 0
    sent = 0
    article_url = frontend_url("article", absolute=True, slug=article.slug)
    connection = _mail_connection()
    try:
        connection.open()
        for subscriber in Subscriber.objects.filter(pk__in=subscriber_ids, status=Subscriber.Status.CONFIRMED):
            key = f"newsletter:{article_id}:{subscriber.pk}"
            if not receipts.claim(key):
                continue
            unsubscribe_url = frontend_url("newsletter_unsubscribe", absolute=True, token=subscriber.token)
            context = {
                "article": article, "subscriber": subscriber, "article_url": article_url,
                "unsubscribe_url": unsubscribe_url, "site_name": blog_settings.SITE_NAME,
            }
            subject = " ".join(render_to_string("flex_blog/email/new_article_subject.txt", context).split())
            body = render_to_string("flex_blog/email/new_article.txt", context)
            message = EmailMultiAlternatives(
                subject, body, _from_email(), [subscriber.email], connection=connection,
                headers={"List-Unsubscribe": f"<{unsubscribe_url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"},
            )
            try:
                message.send()
                sent += 1
            except Exception:
                receipts.release(key)
                logger.exception("flex_blog: newsletter to subscriber %s failed", subscriber.pk)
    finally:
        connection.close()
    return sent

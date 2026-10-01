import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string

from flex_blog.conf import blog_settings
from flex_blog.urls_utils import absolute_url

logger = logging.getLogger("flex_blog")


class BaseBackend:
    """Subclass and implement ``send``. Raise to signal failure (it will be logged)."""

    name = "base"

    def send(self, message):  # pragma: no cover - interface
        raise NotImplementedError


class InAppBackend(BaseBackend):
    """Stores a ``Notification`` row; read it through ``/notifications/``."""

    name = "in_app"

    def send(self, message):
        if not message.recipient_id:
            return
        from flex_blog.models import Notification

        try:
            with transaction.atomic():
                Notification.objects.create(
                    recipient_id=message.recipient_id, event=message.event, title=message.title[:255],
                    body=message.body, url=message.url[:500], data=message.data,
                    dedupe_key=message.dedupe_key or None,
                )
        except IntegrityError:
            pass  # already stored (dedupe_key)


class EmailBackend(BaseBackend):
    """Plain-text email via Django's mail settings. Templates are overridable."""

    name = "email"

    def send(self, message):
        email = message.email
        if not email and message.recipient_id:
            user = message.get_recipient()
            email = getattr(user, "email", "") if user else ""
        if not email:
            return
        context = {"message": message, "site_name": blog_settings.SITE_NAME, "url": absolute_url(message.url) if message.url else ""}
        body = render_to_string("flex_blog/email/notification.txt", context)
        from_email = blog_settings.NOTIFICATIONS["from_email"] or settings.DEFAULT_FROM_EMAIL
        send_mail(message.title, body, from_email, [email])


class LoggingBackend(BaseBackend):
    """Writes notifications to the ``flex_blog`` logger. Handy in development."""

    name = "log"

    def send(self, message):
        logger.info("notification %s to %s: %s", message.event, message.recipient_id or message.email, message.title)

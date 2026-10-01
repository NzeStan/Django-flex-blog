"""
Notifications: who should hear about what, delivered over pluggable channels.

Flow::

    domain event (flex_blog.signals) -> receivers build NotificationMessage(s)
        -> notify() -> background job -> every configured backend .send()

Channels are classes listed in FLEX_BLOG["NOTIFICATIONS"]["backends"]. Ship
your own (SMS, push, Slack, WhatsApp...) by subclassing
``flex_blog.notifications.backends.BaseBackend``::

    class SMSBackend(BaseBackend):
        name = "sms"

        def send(self, message):
            user = message.get_recipient()
            ...

Each (backend, message) pair is delivered at most once thanks to the
message's ``dedupe_key``, even if a job is retried.
"""

import logging
from dataclasses import asdict, dataclass, field

from flex_blog.conf import blog_settings

logger = logging.getLogger("flex_blog")


@dataclass
class NotificationMessage:
    event: str
    title: str
    body: str = ""
    url: str = ""
    recipient_id: str = ""  # user primary key, for in-app and user-aware channels
    email: str = ""  # explicit address (guests, moderators)
    data: dict = field(default_factory=dict)
    dedupe_key: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def get_recipient(self):
        if not self.recipient_id:
            return None
        from django.contrib.auth import get_user_model

        return get_user_model()._default_manager.filter(pk=self.recipient_id).first()


def get_backends():
    return [blog_settings.import_from(path)() for path in blog_settings.NOTIFICATIONS["backends"]]


def notify(message):
    """Queue ``message`` for delivery after the current transaction commits."""
    if not blog_settings.feature_enabled("notifications"):
        return False
    custom_filter = blog_settings.import_from(blog_settings.NOTIFICATIONS["recipient_filter"])
    if custom_filter and not custom_filter(message):
        return False
    from flex_blog.tasks import deliver_notification, enqueue

    enqueue(deliver_notification, message.to_dict())
    return True


def deliver(payload):
    from flex_blog import receipts

    message = NotificationMessage.from_dict(payload)
    for backend in get_backends():
        key = f"notify:{backend.name}:{message.dedupe_key}" if message.dedupe_key else None
        if key and not receipts.claim(key):
            continue
        try:
            backend.send(message)
        except Exception:
            if key:
                receipts.release(key)
            logger.exception("flex_blog: notification backend %s failed for %s", backend.name, message.event)

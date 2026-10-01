"""
Domain events: the public plugin API of django-flex-blog.

Every event is sent *after* the database transaction commits, exactly once
per logical occurrence, and carries a unique ``event_id`` you can use as an
idempotency key in your own receivers. Connect to them like any Django signal::

    from django.dispatch import receiver
    from flex_blog.signals import article_published

    @receiver(article_published)
    def tweet_it(sender, article, event_id, **kwargs):
        ...

Receivers run synchronously in the request (or task) that triggered the
event. Hand slow work to ``flex_blog.tasks.enqueue`` or your own queue.

Events and their keyword arguments (all also receive ``event_id``):

========================  ==============================================
article_published         article
article_unpublished       article
article_viewed            article, user (may be None)
comment_posted            comment (any status, including pending)
comment_approved          comment, moderator (None when auto-approved)
comment_rejected          comment, moderator, status ("rejected"/"spam")
reaction_added            reaction
reaction_removed          article, user, kind
bookmark_added            bookmark
subscriber_confirmed      subscriber
subscriber_unsubscribed   subscriber
========================  ==============================================
"""

import logging
import uuid

from django.db import transaction
from django.dispatch import Signal

logger = logging.getLogger("flex_blog")

article_published = Signal()
article_unpublished = Signal()
article_viewed = Signal()
comment_posted = Signal()
comment_approved = Signal()
comment_rejected = Signal()
reaction_added = Signal()
reaction_removed = Signal()
bookmark_added = Signal()
subscriber_confirmed = Signal()
subscriber_unsubscribed = Signal()

EVENTS = {
    "article_published": article_published,
    "article_unpublished": article_unpublished,
    "article_viewed": article_viewed,
    "comment_posted": comment_posted,
    "comment_approved": comment_approved,
    "comment_rejected": comment_rejected,
    "reaction_added": reaction_added,
    "reaction_removed": reaction_removed,
    "bookmark_added": bookmark_added,
    "subscriber_confirmed": subscriber_confirmed,
    "subscriber_unsubscribed": subscriber_unsubscribed,
}

# Events not forwarded to webhooks (too chatty to POST on every occurrence).
WEBHOOK_EXCLUDED = {"article_viewed"}


def emit(event, sender, **payload):
    """
    Send ``event`` once the current transaction commits (immediately when
    there is none). A failing receiver is logged and never breaks the
    request or the other receivers.
    """
    signal = EVENTS[event]
    event_id = payload.pop("event_id", None) or uuid.uuid4()

    def send():
        for receiver, result in signal.send_robust(sender=sender, event_id=event_id, **payload):
            if isinstance(result, Exception):
                logger.error("flex_blog: receiver %r failed for %s", receiver, event, exc_info=result)
        if event not in WEBHOOK_EXCLUDED:
            from flex_blog.conf import blog_settings

            if blog_settings.feature_enabled("webhooks"):
                from flex_blog import webhooks

                try:
                    webhooks.dispatch(event, event_id, payload)
                except Exception:
                    logger.exception("flex_blog: could not queue webhooks for %s", event)

    transaction.on_commit(send)
    return event_id

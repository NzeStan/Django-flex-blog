"""
Built-in reactions to domain events. Connected in ``AppConfig.ready`` only
for the features you have enabled; each is a normal signal receiver, so you
can disconnect any of them (by ``dispatch_uid``) and plug in your own.
"""

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.utils.translation import gettext as _

from flex_blog import signals
from flex_blog.conf import blog_settings
from flex_blog.notifications import NotificationMessage, notify
from flex_blog.urls_utils import frontend_url

# --- response cache invalidation --------------------------------------------


def invalidate_cache(sender, **kwargs):
    if not blog_settings.feature_enabled("response_cache"):
        return
    from flex_blog.cache import bump_version

    bump_version()


# --- newsletter ---------------------------------------------------------------


def newsletter_on_publish(sender, article, **kwargs):
    if not blog_settings.feature_enabled("newsletter") or not blog_settings.NEWSLETTER["send_on_publish"]:
        return
    from flex_blog.tasks import enqueue, send_newsletter_for_article

    enqueue(send_newsletter_for_article, str(article.pk))


# --- notifications ------------------------------------------------------------


def _comment_url(comment):
    return frontend_url("article", slug=comment.article.slug) + f"#comment-{comment.pk}"


def notify_comment_approved(sender, comment, moderator=None, **kwargs):
    if not blog_settings.feature_enabled("notifications"):
        return
    events = blog_settings.NOTIFICATIONS["events"]
    article = comment.article
    commenter_id = str(comment.user_id) if comment.user_id else ""
    data = {"article": article.slug, "comment": str(comment.pk)}
    notified = {commenter_id} if commenter_id else set()

    if events.get("comment_reply") and comment.parent_id:
        parent = comment.parent
        if parent.user_id and str(parent.user_id) not in notified:
            notify(NotificationMessage(
                event="comment_reply", recipient_id=str(parent.user_id),
                title=_("%(name)s replied to your comment") % {"name": comment.display_name},
                body=comment.content[:500], url=_comment_url(comment), data=data,
                dedupe_key=f"comment_reply:{comment.pk}",
            ))
            notified.add(str(parent.user_id))
        elif not parent.user_id and parent.author_email:
            notify(NotificationMessage(
                event="comment_reply", email=parent.author_email,
                title=_("%(name)s replied to your comment") % {"name": comment.display_name},
                body=comment.content[:500], url=_comment_url(comment), data=data,
                dedupe_key=f"comment_reply:{comment.pk}",
            ))

    if events.get("comment_on_article") and article.author_id:
        author_user_id = str(article.author.user_id)
        if author_user_id not in notified:
            notify(NotificationMessage(
                event="comment_on_article", recipient_id=author_user_id,
                title=_("New comment on “%(title)s”") % {"title": article.title},
                body=comment.content[:500], url=_comment_url(comment), data=data,
                dedupe_key=f"comment_on_article:{comment.pk}",
            ))

    if events.get("comment_approved") and moderator is not None and (commenter_id or comment.author_email):
        notify(NotificationMessage(
            event="comment_approved", recipient_id=commenter_id, email="" if commenter_id else comment.author_email,
            title=_("Your comment on “%(title)s” was approved") % {"title": article.title},
            url=_comment_url(comment), data=data, dedupe_key=f"comment_approved:{comment.pk}",
        ))


def notify_comment_pending(sender, comment, **kwargs):
    from flex_blog.models import Comment

    if not blog_settings.feature_enabled("notifications"):
        return
    if comment.status != Comment.Status.PENDING or not blog_settings.NOTIFICATIONS["events"].get("comment_pending"):
        return
    for email in blog_settings.NOTIFICATIONS["moderator_emails"]:
        notify(NotificationMessage(
            event="comment_pending", email=email,
            title=_("Comment awaiting moderation on “%(title)s”") % {"title": comment.article.title},
            body=comment.content[:500], url=_comment_url(comment),
            data={"article": comment.article.slug, "comment": str(comment.pk)},
            dedupe_key=f"comment_pending:{comment.pk}:{email}",
        ))


def connect():
    """Connect the built-in receivers. Each one checks its feature flag when it runs."""
    from flex_blog import models

    for model in (models.Article, models.Author, models.Category, models.Tag, models.Series, models.Comment):
        post_save.connect(invalidate_cache, sender=model, dispatch_uid=f"flex_blog.cache.save.{model.__name__}")
        post_delete.connect(invalidate_cache, sender=model, dispatch_uid=f"flex_blog.cache.delete.{model.__name__}")
    for through in (models.Article.tags.through, models.Article.categories.through):
        m2m_changed.connect(invalidate_cache, sender=through, dispatch_uid=f"flex_blog.cache.m2m.{through.__name__}")
    for event in ("comment_approved", "comment_rejected", "article_published", "article_unpublished"):
        signals.EVENTS[event].connect(invalidate_cache, dispatch_uid=f"flex_blog.cache.{event}")

    signals.article_published.connect(newsletter_on_publish, dispatch_uid="flex_blog.newsletter.on_publish")
    signals.comment_approved.connect(notify_comment_approved, dispatch_uid="flex_blog.notify.comment_approved")
    signals.comment_posted.connect(notify_comment_pending, dispatch_uid="flex_blog.notify.comment_pending")

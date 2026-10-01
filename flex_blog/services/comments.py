import ipaddress
import logging
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext as _

from flex_blog.conf import blog_settings
from flex_blog.models import Article, Comment, CommentFlag
from flex_blog.permissions import is_moderator
from flex_blog.rendering import count_links
from flex_blog.signals import emit

logger = logging.getLogger("flex_blog")


def comments_open(article):
    if not blog_settings.feature_enabled("comments") or not article.allow_comments or not article.is_live:
        return False
    days = blog_settings.COMMENTS["close_after_days"]
    if days and article.published_at < timezone.now() - timedelta(days=days):
        return False
    return True


def _initial_status(user):
    mode = blog_settings.COMMENTS["moderation"]
    authenticated = bool(user and user.is_authenticated)
    if authenticated and is_moderator(user):
        return Comment.Status.APPROVED
    if mode == "none":
        return Comment.Status.APPROVED
    if mode == "anonymous":
        return Comment.Status.APPROVED if authenticated else Comment.Status.PENDING
    if mode == "first_time":
        if authenticated and Comment.objects.filter(user=user, status=Comment.Status.APPROVED).exists():
            return Comment.Status.APPROVED
        return Comment.Status.PENDING
    return Comment.Status.PENDING


def validate_content(content):
    conf = blog_settings.COMMENTS
    content = (content or "").strip()
    if len(content) < conf["min_length"]:
        raise ValidationError({"content": _("Comment is too short.")})
    if len(content) > conf["max_length"]:
        raise ValidationError({"content": _("Comment is too long (max %(n)s characters).") % {"n": conf["max_length"]}})
    if conf["max_links"] is not None and count_links(content) > conf["max_links"]:
        raise ValidationError({"content": _("Too many links in this comment.")})
    lowered = content.lower()
    if any(word.lower() in lowered for word in conf["blocked_words"]):
        raise ValidationError({"content": _("This comment contains blocked words.")})
    return content


def _safe_ip(value):
    try:
        return str(ipaddress.ip_address((value or "").strip()))
    except ValueError:
        return None


def create(article, *, user=None, content, parent=None, author_name="", author_email="", author_url="", request=None):
    if not comments_open(article):
        raise PermissionDenied(_("Comments are closed for this article."))
    authenticated = bool(user and user.is_authenticated)
    if not authenticated:
        if not blog_settings.COMMENTS["allow_anonymous"]:
            raise PermissionDenied(_("You must be signed in to comment."))
        if not author_name.strip() or not author_email.strip():
            raise ValidationError({"author_name": _("Name and email are required.")})
    content = validate_content(content)
    if parent is not None:
        if parent.article_id != article.pk:
            raise ValidationError({"parent": _("You can only reply to comments on the same article.")})
        if parent.status != Comment.Status.APPROVED or parent.is_removed:
            raise ValidationError({"parent": _("You cannot reply to this comment.")})
        if parent.depth + 1 > blog_settings.COMMENTS["max_depth"]:
            raise ValidationError({"parent": _("Replies are nested too deeply.")})

    comment = Comment(
        article=article,
        parent=parent,
        user=user if authenticated else None,
        author_name="" if authenticated else author_name.strip()[:100],
        author_email="" if authenticated else author_email.strip().lower(),
        author_url="" if authenticated else author_url.strip(),
        content=content,
        status=_initial_status(user),
    )
    if request is not None:
        from flex_blog.utils import client_ip

        comment.user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]
        if blog_settings.COMMENTS["store_ip_address"]:
            comment.ip_address = _safe_ip(client_ip(request))

    checker = blog_settings.import_from(blog_settings.COMMENTS["spam_checker"])
    if checker:
        try:
            if checker(comment, request):
                comment.status = Comment.Status.SPAM
        except Exception:
            logger.exception("flex_blog: spam checker failed; holding comment for moderation")
            comment.status = Comment.Status.PENDING

    with transaction.atomic():
        comment.save()
        if comment.status == Comment.Status.APPROVED:
            Article.objects.filter(pk=article.pk).update(comment_count=F("comment_count") + 1)
    emit("comment_posted", sender=Comment, comment=comment)
    if comment.status == Comment.Status.APPROVED:
        emit("comment_approved", sender=Comment, comment=comment, moderator=None)
    return comment


def moderate(comment_id, status, moderator=None):
    """
    Move a comment to ``status``. Row-locked so concurrent moderators can't
    double count; repeating the same decision is a no-op (idempotent).
    """
    if status not in Comment.Status.values:
        raise ValidationError({"status": _("Unknown status.")})
    with transaction.atomic():
        comment = Comment.objects.select_for_update().get(pk=comment_id)
        previous = comment.status
        if previous == status:
            return comment, False
        comment.status = status
        comment.save(update_fields=["status", "updated_at", "depth", "content_html"])
        counted_before = previous == Comment.Status.APPROVED and not comment.is_removed
        counted_after = status == Comment.Status.APPROVED and not comment.is_removed
        delta = int(counted_after) - int(counted_before)
        if delta:
            Article.objects.filter(pk=comment.article_id).update(comment_count=F("comment_count") + delta)
    if status == Comment.Status.APPROVED:
        emit("comment_approved", sender=Comment, comment=comment, moderator=moderator)
    elif status in (Comment.Status.REJECTED, Comment.Status.SPAM):
        emit("comment_rejected", sender=Comment, comment=comment, moderator=moderator, status=status)
    return comment, True


def edit(comment, user, content):
    if not is_moderator(user):
        window = blog_settings.COMMENTS["edit_window_minutes"]
        if comment.user_id != user.pk:
            raise PermissionDenied(_("You can only edit your own comments."))
        if comment.is_removed:
            raise PermissionDenied(_("This comment was removed."))
        if window is not None and comment.created_at < timezone.now() - timedelta(minutes=window):
            raise PermissionDenied(_("The time to edit this comment has passed."))
    comment.content = validate_content(content)
    comment.edited_at = timezone.now()
    comment.save()
    return comment


def remove(comment, user):
    """
    Soft-delete: content disappears but the row stays so replies keep their
    thread. Moderators hard-delete threads through the admin.
    """
    with transaction.atomic():
        comment = Comment.objects.select_for_update().get(pk=comment.pk)
        if comment.is_removed:
            return comment
        comment.is_removed = True
        comment.save(update_fields=["is_removed", "updated_at", "depth", "content_html"])
        if comment.status == Comment.Status.APPROVED:
            Article.objects.filter(pk=comment.article_id, comment_count__gt=0).update(comment_count=F("comment_count") - 1)
    return comment


def flag(comment, user, reason=""):
    """One flag per user (idempotent). Enough flags send it back to moderation."""
    try:
        with transaction.atomic():
            CommentFlag.objects.create(comment=comment, user=user, reason=(reason or "")[:255])
            Comment.objects.filter(pk=comment.pk).update(flag_count=F("flag_count") + 1)
    except IntegrityError:
        return False
    threshold = blog_settings.COMMENTS.get("flag_threshold", 5)
    comment.refresh_from_db(fields=["flag_count", "status"])
    if threshold and comment.flag_count >= threshold and comment.status == Comment.Status.APPROVED:
        moderate(comment.pk, Comment.Status.PENDING)
    return True

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from flex_blog.models.base import BaseModel, ExtraDataMixin


class CommentQuerySet(models.QuerySet):
    def approved(self):
        return self.filter(status=Comment.Status.APPROVED)

    def visible_to(self, user):
        """Approved comments, plus the user's own pending ones; moderators see all."""
        if user and user.is_authenticated:
            if user.has_perm("flex_blog.moderate_comment"):
                return self
            return self.filter(models.Q(status=Comment.Status.APPROVED) | models.Q(user=user, status=Comment.Status.PENDING))
        return self.approved()


class Comment(BaseModel, ExtraDataMixin):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending moderation")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        SPAM = "spam", _("Spam")

    article = models.ForeignKey("flex_blog.Article", on_delete=models.CASCADE, related_name="comments", verbose_name=_("article"))
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True,
        related_name="replies", verbose_name=_("in reply to"),
    )
    depth = models.PositiveSmallIntegerField(_("depth"), default=0, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="blog_comments", verbose_name=_("user"),
    )
    author_name = models.CharField(_("name"), max_length=100, blank=True)
    author_email = models.EmailField(_("email"), blank=True)
    author_url = models.URLField(_("website"), blank=True)

    content = models.TextField(_("content"))
    content_html = models.TextField(_("rendered content"), blank=True, editable=False)
    status = models.CharField(_("status"), max_length=20, choices=Status.choices, default=Status.PENDING)
    is_removed = models.BooleanField(_("removed"), default=False, help_text=_("Removed by its author; kept so replies stay threaded."))
    edited_at = models.DateTimeField(_("edited at"), null=True, blank=True)
    flag_count = models.PositiveIntegerField(_("flags"), default=0, editable=False)

    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.CharField(_("user agent"), max_length=255, blank=True)

    objects = CommentQuerySet.as_manager()

    class Meta:
        verbose_name = _("comment")
        verbose_name_plural = _("comments")
        ordering = ["created_at"]
        permissions = [("moderate_comment", _("Can moderate comments"))]
        indexes = [
            models.Index(fields=["article", "status", "created_at"], name="flexblog_cmt_article"),
            models.Index(fields=["status", "-created_at"], name="flexblog_cmt_status"),
        ]

    def __str__(self):
        return _("Comment by %(name)s on %(article)s") % {"name": self.display_name, "article": self.article_id}

    @property
    def display_name(self):
        if self.user_id:
            author = getattr(self.user, "blog_author", None)
            if author is not None:
                return author.display_name
            return (self.user.get_full_name() if hasattr(self.user, "get_full_name") else "") or self.user.get_username()
        return self.author_name or _("Anonymous")

    @property
    def notify_email(self):
        return (self.user.email if self.user_id else self.author_email) or ""

    def save(self, *args, **kwargs):
        from flex_blog.rendering import render_comment

        self.depth = (self.parent.depth + 1) if self.parent_id else 0
        self.content_html = render_comment(self.content)
        super().save(*args, **kwargs)


class CommentFlag(BaseModel):
    """A reader reporting a comment. One flag per user per comment."""

    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="flags")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    reason = models.CharField(_("reason"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("comment flag")
        verbose_name_plural = _("comment flags")
        constraints = [models.UniqueConstraint(fields=["comment", "user"], name="flexblog_unique_comment_flag")]

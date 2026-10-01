import secrets

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from flex_blog.models.base import BaseModel


class Reaction(BaseModel):
    """A user's reaction to an article. Unique per (article, user, kind)."""

    article = models.ForeignKey("flex_blog.Article", on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blog_reactions")
    kind = models.CharField(_("kind"), max_length=30, default="like")

    class Meta:
        verbose_name = _("reaction")
        verbose_name_plural = _("reactions")
        constraints = [models.UniqueConstraint(fields=["article", "user", "kind"], name="flexblog_unique_reaction")]
        indexes = [models.Index(fields=["article", "kind"], name="flexblog_reaction_kind")]

    def __str__(self):
        return f"{self.user_id} {self.kind} {self.article_id}"


class Bookmark(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blog_bookmarks")
    article = models.ForeignKey("flex_blog.Article", on_delete=models.CASCADE, related_name="bookmarks")

    class Meta:
        verbose_name = _("bookmark")
        verbose_name_plural = _("bookmarks")
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "article"], name="flexblog_unique_bookmark")]

    def __str__(self):
        return f"{self.user_id} → {self.article_id}"


def _subscriber_token():
    return secrets.token_urlsafe(32)


class Subscriber(BaseModel):
    """Newsletter subscriber with double opt-in."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending confirmation")
        CONFIRMED = "confirmed", _("Confirmed")
        UNSUBSCRIBED = "unsubscribed", _("Unsubscribed")

    email = models.EmailField(_("email"), unique=True)
    name = models.CharField(_("name"), max_length=150, blank=True)
    status = models.CharField(_("status"), max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    # Secret used in unsubscribe links. Rotated on resubscribe.
    token = models.CharField(_("token"), max_length=64, unique=True, default=_subscriber_token, editable=False)
    language = models.CharField(_("language"), max_length=15, blank=True)
    source = models.CharField(_("source"), max_length=100, blank=True)
    confirmed_at = models.DateTimeField(_("confirmed at"), null=True, blank=True)
    unsubscribed_at = models.DateTimeField(_("unsubscribed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("newsletter subscriber")
        verbose_name_plural = _("newsletter subscribers")
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

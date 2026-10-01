from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from flex_blog.models.base import BaseModel, ExtraDataMixin, SlugMixin
from flex_blog.models.media import media_storage, upload_to
from flex_blog.urls_utils import frontend_url
from flex_blog.validators import validate_image_upload


class Author(SlugMixin, BaseModel, ExtraDataMixin):
    """Public profile of a writer. One per user; created on demand."""

    slug_source = "display_name"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="blog_author", verbose_name=_("user"),
    )
    display_name = models.CharField(_("display name"), max_length=150)
    bio = models.TextField(_("biography"), blank=True)
    avatar = models.ImageField(
        _("avatar"), upload_to=upload_to, storage=media_storage, blank=True,
        max_length=255, validators=[validate_image_upload],
    )
    website = models.URLField(_("website"), blank=True)
    social_links = models.JSONField(_("social links"), default=dict, blank=True)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    class Meta:
        verbose_name = _("author")
        verbose_name_plural = _("authors")
        ordering = ["display_name"]

    def __str__(self):
        return self.display_name

    def clean(self):
        if self.social_links and not isinstance(self.social_links, dict):
            raise ValidationError({"social_links": _("Must be an object of name -> URL.")})

    def get_absolute_url(self):
        return frontend_url("author", slug=self.slug)

    @classmethod
    def for_user(cls, user):
        """Return the user's author profile, creating it on first use (race safe)."""
        name = (user.get_full_name() if hasattr(user, "get_full_name") else "") or user.get_username()
        author, _created = cls.objects.get_or_create(user=user, defaults={"display_name": name[:150]})
        return author


class Category(SlugMixin, BaseModel, ExtraDataMixin):
    """Hierarchical category (a plain adjacency list; trees are built in one query)."""

    name = models.CharField(_("name"), max_length=150)
    description = models.TextField(_("description"), blank=True)
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="children", verbose_name=_("parent"),
    )
    order = models.IntegerField(_("order"), default=0, db_index=True)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)
    meta_title = models.CharField(_("meta title"), max_length=255, blank=True)
    meta_description = models.CharField(_("meta description"), max_length=320, blank=True)

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def clean(self):
        node, seen = self.parent, set()
        while node is not None:
            if node.pk == self.pk or node.pk in seen:
                raise ValidationError({"parent": _("A category cannot be its own ancestor.")})
            seen.add(node.pk)
            node = node.parent

    def get_absolute_url(self):
        return frontend_url("category", slug=self.slug)

    def get_descendant_ids(self):
        """IDs of this category and every category below it."""
        pairs = list(Category.objects.values_list("pk", "parent_id"))
        children = {}
        for pk, parent_id in pairs:
            children.setdefault(parent_id, []).append(pk)
        result, stack = set(), [self.pk]
        while stack:
            pk = stack.pop()
            if pk not in result:
                result.add(pk)
                stack.extend(children.get(pk, []))
        return list(result)


class Tag(SlugMixin, BaseModel):
    name = models.CharField(_("name"), max_length=100)
    description = models.TextField(_("description"), blank=True)

    class Meta:
        verbose_name = _("tag")
        verbose_name_plural = _("tags")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return frontend_url("tag", slug=self.slug)


class Series(SlugMixin, BaseModel, ExtraDataMixin):
    """An ordered collection of articles (a course, a multi-part story...)."""

    slug_source = "title"

    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(_("description"), blank=True)
    author = models.ForeignKey(
        "flex_blog.Author", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="series", verbose_name=_("author"),
    )
    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    class Meta:
        verbose_name = _("series")
        verbose_name_plural = _("series")
        ordering = ["title"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return frontend_url("series", slug=self.slug)

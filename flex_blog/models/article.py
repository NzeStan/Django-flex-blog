from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from flex_blog.conf import blog_settings
from flex_blog.models.base import BaseModel, ExtraDataMixin, SlugMixin
from flex_blog.models.media import media_storage, upload_to
from flex_blog.urls_utils import frontend_url
from flex_blog.validators import validate_image_upload

# Fields whose change produces a revision and re-rendering.
CONTENT_FIELDS = ("title", "subtitle", "summary", "content", "content_format")


class ArticleQuerySet(models.QuerySet):
    def published(self):
        """Live now: published status and a publication date that has passed."""
        return self.filter(status=Article.Status.PUBLISHED, published_at__lte=timezone.now())

    def scheduled(self):
        return self.filter(status=Article.Status.PUBLISHED, published_at__gt=timezone.now())

    def listed(self):
        """What appears in public feeds: published and not unlisted."""
        return self.published().exclude(visibility=Article.Visibility.UNLISTED)

    def owned_by(self, user):
        if not user or not user.is_authenticated:
            return self.none()
        return self.filter(author__user=user)

    def readable_by(self, user):
        """Everything ``user`` may open by URL: published, own, or all for editors."""
        if user and user.is_authenticated and user.has_perm("flex_blog.change_article"):
            return self
        if user and user.is_authenticated:
            return self.filter(
                Q(status=Article.Status.PUBLISHED, published_at__lte=timezone.now()) | Q(author__user=user)
            )
        return self.published()

    def with_relations(self):
        return self.select_related("author", "series").prefetch_related("categories", "tags")


class Article(SlugMixin, BaseModel, ExtraDataMixin):
    slug_source = "title"

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        REVIEW = "review", _("Pending review")
        PUBLISHED = "published", _("Published")
        ARCHIVED = "archived", _("Archived")

    class Visibility(models.TextChoices):
        PUBLIC = "public", _("Public")
        UNLISTED = "unlisted", _("Unlisted (link only)")
        MEMBERS = "members", _("Members only")

    class ContentFormat(models.TextChoices):
        MARKDOWN = "markdown", _("Markdown")
        HTML = "html", _("HTML")
        PLAIN = "plain", _("Plain text")

    title = models.CharField(_("title"), max_length=255)
    subtitle = models.CharField(_("subtitle"), max_length=255, blank=True)
    summary = models.TextField(_("summary"), blank=True, help_text=_("Leave empty to generate from the content."))
    content = models.TextField(_("content"), blank=True)
    content_format = models.CharField(_("content format"), max_length=20, choices=ContentFormat.choices, default=ContentFormat.MARKDOWN)

    # Derived on save; never edited directly.
    content_html = models.TextField(_("rendered content"), blank=True, editable=False)
    excerpt = models.TextField(_("excerpt"), blank=True, editable=False)
    table_of_contents = models.JSONField(_("table of contents"), default=list, blank=True, editable=False)
    word_count = models.PositiveIntegerField(_("word count"), default=0, editable=False)
    reading_time = models.PositiveIntegerField(_("reading time (minutes)"), default=0, editable=False)

    author = models.ForeignKey(
        "flex_blog.Author", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="articles", verbose_name=_("author"),
    )
    categories = models.ManyToManyField("flex_blog.Category", blank=True, related_name="articles", verbose_name=_("categories"))
    tags = models.ManyToManyField("flex_blog.Tag", blank=True, related_name="articles", verbose_name=_("tags"))
    series = models.ForeignKey(
        "flex_blog.Series", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="articles", verbose_name=_("series"),
    )
    series_order = models.PositiveIntegerField(_("position in series"), default=0)

    cover_image = models.ImageField(
        _("cover image"), upload_to=upload_to, storage=media_storage, blank=True,
        max_length=255, validators=[validate_image_upload],
    )
    cover_image_alt = models.CharField(_("cover image alt text"), max_length=255, blank=True)

    status = models.CharField(_("status"), max_length=20, choices=Status.choices, default=Status.DRAFT)
    visibility = models.CharField(_("visibility"), max_length=20, choices=Visibility.choices, default=Visibility.PUBLIC)
    published_at = models.DateTimeField(
        _("published at"), null=True, blank=True,
        help_text=_("Set a future date to schedule publication."),
    )
    # When the "article_published" event fired; guarantees it fires once.
    announced_at = models.DateTimeField(_("announced at"), null=True, blank=True, editable=False)

    is_featured = models.BooleanField(_("featured"), default=False)
    is_pinned = models.BooleanField(_("pinned"), default=False)
    allow_comments = models.BooleanField(_("allow comments"), default=True)
    language = models.CharField(_("language"), max_length=15, blank=True, db_index=True)

    meta_title = models.CharField(_("meta title"), max_length=255, blank=True)
    meta_description = models.CharField(_("meta description"), max_length=320, blank=True)
    canonical_url = models.URLField(_("canonical URL"), blank=True)
    noindex = models.BooleanField(_("hide from search engines"), default=False)

    # Denormalised counters, only ever changed with atomic F() updates.
    views_count = models.PositiveBigIntegerField(_("views"), default=0, editable=False)
    comment_count = models.PositiveIntegerField(_("comments"), default=0, editable=False)
    reaction_count = models.PositiveIntegerField(_("reactions"), default=0, editable=False)

    # Optimistic locking: bumped on every save, checked on API updates.
    version = models.PositiveIntegerField(_("version"), default=1, editable=False)

    objects = ArticleQuerySet.as_manager()

    class Meta:
        verbose_name = _("article")
        verbose_name_plural = _("articles")
        ordering = ["-published_at", "-created_at"]
        permissions = [("publish_article", _("Can publish articles"))]
        indexes = [
            models.Index(fields=["status", "published_at"], name="flexblog_art_status_pub"),
            models.Index(fields=["status", "visibility", "-published_at"], name="flexblog_art_feed"),
            models.Index(fields=["author", "status"], name="flexblog_art_author_status"),
            models.Index(fields=["is_featured", "-published_at"], name="flexblog_art_featured"),
            models.Index(fields=["-views_count"], name="flexblog_art_views"),
        ]

    def __str__(self):
        return self.title

    @classmethod
    def from_db(cls, db, field_names, values, *args, **kwargs):
        instance = super().from_db(db, field_names, values, *args, **kwargs)
        instance._loaded = {name: getattr(instance, name) for name in (*CONTENT_FIELDS, "status", "slug", "published_at") if name in field_names}
        return instance

    def _changed(self, name):
        loaded = getattr(self, "_loaded", None)
        if loaded is None or name not in loaded:
            return True
        return loaded[name] != getattr(self, name)

    @property
    def is_live(self):
        return self.status == self.Status.PUBLISHED and self.published_at is not None and self.published_at <= timezone.now()

    @property
    def is_scheduled(self):
        return self.status == self.Status.PUBLISHED and self.published_at is not None and self.published_at > timezone.now()

    def get_absolute_url(self):
        return frontend_url("article", slug=self.slug)

    def save(self, *args, **kwargs):
        adding = self._state.adding
        if adding or any(self._changed(f) for f in ("content", "content_format")) or not self.content_html:
            self.render()
        elif self._changed("summary"):
            self._refresh_excerpt()
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        old_slug = None if adding else (getattr(self, "_loaded", {}) or {}).get("slug")
        content_changed = not adding and any(self._changed(f) for f in CONTENT_FIELDS)
        was_live = not adding and (getattr(self, "_loaded", {}) or {}).get("status") == self.Status.PUBLISHED
        if not adding:
            self.version = (self.version or 0) + 1
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = {*kwargs["update_fields"], "version", "updated_at"}
        super().save(*args, **kwargs)

        if old_slug and old_slug != self.slug and blog_settings.feature_enabled("slug_redirects"):
            SlugRedirect.objects.filter(old_slug=self.slug).delete()
            SlugRedirect.objects.update_or_create(old_slug=old_slug, defaults={"article": self})
        if content_changed and blog_settings.feature_enabled("revisions"):
            ArticleRevision.capture(self, editor=getattr(self, "_editor", None), previous=self._loaded)
        self._after_status_change(was_live)
        self._loaded = {name: getattr(self, name) for name in (*CONTENT_FIELDS, "status", "slug", "published_at")}

    def _after_status_change(self, was_live):
        from flex_blog import services

        if self.is_live and not self.announced_at:
            pk = self.pk
            transaction.on_commit(lambda: services.articles.announce(pk))
        elif was_live and self.status != self.Status.PUBLISHED:
            services.articles.emit_unpublished(self)

    def render(self):
        from flex_blog.rendering import render_content

        rendered = render_content(self.content, self.content_format)
        self.content_html = rendered.html
        self.table_of_contents = rendered.toc
        self.word_count = rendered.word_count
        self.reading_time = rendered.reading_time
        self._plain_text = rendered.text
        self._refresh_excerpt()

    def _refresh_excerpt(self):
        from flex_blog.rendering import html_to_text, make_excerpt

        text = self.summary or getattr(self, "_plain_text", None) or html_to_text(self.content_html)
        self.excerpt = make_excerpt(text)


class ArticleRevision(BaseModel):
    """Snapshot of an article's content before each edit."""

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="revisions", verbose_name=_("article"))
    version = models.PositiveIntegerField(_("version"))
    title = models.CharField(_("title"), max_length=255)
    subtitle = models.CharField(_("subtitle"), max_length=255, blank=True)
    summary = models.TextField(_("summary"), blank=True)
    content = models.TextField(_("content"), blank=True)
    content_format = models.CharField(_("content format"), max_length=20)
    editor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name=_("editor"),
    )

    class Meta:
        verbose_name = _("article revision")
        verbose_name_plural = _("article revisions")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["article", "-created_at"], name="flexblog_rev_article")]

    def __str__(self):
        return f"{self.article} (v{self.version})"

    @classmethod
    def capture(cls, article, editor=None, previous=None):
        """Store the state *before* this edit, so every past version can be restored."""
        previous = previous or {}
        return cls.objects.create(
            article=article,
            version=max(article.version - 1, 1),
            editor=editor if editor is not None and getattr(editor, "is_authenticated", False) else None,
            **{f: previous.get(f, getattr(article, f)) for f in CONTENT_FIELDS},
        )


class SlugRedirect(BaseModel):
    """Old slugs of an article, so links keep working after a rename."""

    old_slug = models.SlugField(_("old slug"), max_length=255, unique=True, allow_unicode=True)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="slug_redirects")

    class Meta:
        verbose_name = _("slug redirect")
        verbose_name_plural = _("slug redirects")

    def __str__(self):
        return f"{self.old_slug} → {self.article.slug}"

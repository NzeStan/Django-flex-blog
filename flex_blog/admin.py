"""
Admin for every model. Bulk actions go through the service layer, so events
(notifications, webhooks, newsletters) fire exactly as they do from the API.
Disable it all with FEATURES["admin"] = False and register your own.
"""

from django.contrib import admin, messages
from django.db.models import Count
from django.template.defaultfilters import filesizeformat
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from flex_blog import models
from flex_blog.conf import blog_settings
from flex_blog.services import articles as article_service
from flex_blog.services import comments as comment_service


class ArticleRevisionInline(admin.TabularInline):
    model = models.ArticleRevision
    extra = 0
    can_delete = False
    fields = ["version", "title", "editor", "created_at"]
    readonly_fields = fields
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False


class ArticleAdmin(admin.ModelAdmin):
    list_display = ["title", "author", "status", "visibility", "published_at", "is_featured", "views_count", "comment_count"]
    list_filter = ["status", "visibility", "is_featured", "is_pinned", "language", "categories"]
    list_select_related = ["author"]
    search_fields = ["title", "subtitle", "summary", "slug"]
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "published_at"
    autocomplete_fields = ["author", "categories", "tags", "series"]
    readonly_fields = ["reading_time", "word_count", "views_count", "comment_count", "reaction_count", "version", "announced_at", "created_at", "updated_at"]
    actions = ["publish", "unpublish", "archive", "feature", "unfeature"]
    fieldsets = (
        (None, {"fields": ("title", "subtitle", "slug", "summary", "content", "content_format")}),
        (_("Organisation"), {"fields": ("author", "categories", "tags", "series", "series_order", "language")}),
        (_("Cover"), {"fields": ("cover_image", "cover_image_alt")}),
        (_("Publication"), {"fields": ("status", "visibility", "published_at", "allow_comments", "is_featured", "is_pinned")}),
        (_("SEO"), {"fields": ("meta_title", "meta_description", "canonical_url", "noindex"), "classes": ("collapse",)}),
        (_("Statistics"), {
            "fields": ("reading_time", "word_count", "views_count", "comment_count", "reaction_count",
                       "version", "announced_at", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
        (_("Advanced"), {"fields": ("extra_data",), "classes": ("collapse",)}),
    )

    def get_inlines(self, request, obj):
        return [ArticleRevisionInline] if obj and blog_settings.feature_enabled("revisions") else []

    def save_model(self, request, obj, form, change):
        obj._editor = request.user
        if obj.author_id is None:
            obj.author = models.Author.for_user(request.user)
        super().save_model(request, obj, form, change)

    def has_publish_permission(self, request):
        return request.user.has_perm("flex_blog.publish_article")

    @admin.action(description=_("Publish selected articles"), permissions=["publish"])
    def publish(self, request, queryset):
        for article in queryset:
            article_service.publish(article, user=request.user)
        self.message_user(request, _("Published %(n)d articles.") % {"n": queryset.count()}, messages.SUCCESS)

    @admin.action(description=_("Move selected articles back to draft"), permissions=["publish"])
    def unpublish(self, request, queryset):
        for article in queryset:
            article_service.unpublish(article, user=request.user)

    @admin.action(description=_("Archive selected articles"), permissions=["publish"])
    def archive(self, request, queryset):
        for article in queryset:
            article_service.unpublish(article, user=request.user, status=models.Article.Status.ARCHIVED)

    @admin.action(description=_("Feature selected articles"), permissions=["change"])
    def feature(self, request, queryset):
        queryset.update(is_featured=True)

    @admin.action(description=_("Un-feature selected articles"), permissions=["change"])
    def unfeature(self, request, queryset):
        queryset.update(is_featured=False)


class AuthorAdmin(admin.ModelAdmin):
    list_display = ["display_name", "user", "slug", "is_active", "article_total"]
    list_filter = ["is_active"]
    search_fields = ["display_name", "slug", "user__username", "user__email"]
    raw_id_fields = ["user"]
    prepopulated_fields = {"slug": ("display_name",)}

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user").annotate(article_total=Count("articles"))

    @admin.display(description=_("Articles"), ordering="article_total")
    def article_total(self, obj):
        return obj.article_total


class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "parent", "slug", "order", "is_active"]
    list_editable = ["order", "is_active"]
    list_filter = ["is_active", "parent"]
    search_fields = ["name", "slug", "description"]
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["parent"]


class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "article_total"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(article_total=Count("articles"))

    @admin.display(description=_("Articles"), ordering="article_total")
    def article_total(self, obj):
        return obj.article_total


class SeriesAdmin(admin.ModelAdmin):
    list_display = ["title", "author", "is_active"]
    search_fields = ["title", "slug"]
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ["author"]


class CommentAdmin(admin.ModelAdmin):
    list_display = ["short_content", "who", "article", "status", "flag_count", "is_removed", "created_at"]
    list_filter = ["status", "is_removed", "created_at"]
    list_select_related = ["article", "user"]
    search_fields = ["content", "author_name", "author_email", "user__username", "article__title"]
    raw_id_fields = ["article", "parent", "user"]
    readonly_fields = ["depth", "flag_count", "ip_address", "user_agent", "created_at", "edited_at"]
    actions = ["approve", "reject", "mark_spam"]

    @admin.display(description=_("Comment"))
    def short_content(self, obj):
        return (obj.content[:80] + "…") if len(obj.content) > 80 else obj.content

    @admin.display(description=_("Author"))
    def who(self, obj):
        return obj.display_name

    def has_moderate_permission(self, request):
        return request.user.has_perm("flex_blog.moderate_comment")

    def _moderate(self, request, queryset, status):
        for pk in queryset.values_list("pk", flat=True):
            comment_service.moderate(pk, status, moderator=request.user)

    @admin.action(description=_("Approve selected comments"), permissions=["moderate"])
    def approve(self, request, queryset):
        self._moderate(request, queryset, models.Comment.Status.APPROVED)

    @admin.action(description=_("Reject selected comments"), permissions=["moderate"])
    def reject(self, request, queryset):
        self._moderate(request, queryset, models.Comment.Status.REJECTED)

    @admin.action(description=_("Mark selected comments as spam"), permissions=["moderate"])
    def mark_spam(self, request, queryset):
        self._moderate(request, queryset, models.Comment.Status.SPAM)


class MediaAdmin(admin.ModelAdmin):
    list_display = ["__str__", "kind", "human_size", "uploaded_by", "created_at"]
    list_filter = ["kind", "created_at"]
    search_fields = ["title", "alt_text", "caption"]
    readonly_fields = ["preview", "kind", "mime_type", "size", "width", "height", "created_at"]
    raw_id_fields = ["uploaded_by"]

    @admin.display(description=_("Size"), ordering="size")
    def human_size(self, obj):
        return filesizeformat(obj.size)

    @admin.display(description=_("Preview"))
    def preview(self, obj):
        if obj.kind == models.Media.Kind.IMAGE and obj.file:
            return format_html('<img src="{}" alt="{}" style="max-width:320px;max-height:240px">', obj.url, obj.alt_text)
        return "—"

    def save_model(self, request, obj, form, change):
        if not obj.uploaded_by_id:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)


class SubscriberAdmin(admin.ModelAdmin):
    list_display = ["email", "name", "status", "source", "confirmed_at", "created_at"]
    list_filter = ["status", "source", "language"]
    search_fields = ["email", "name"]
    readonly_fields = ["confirmed_at", "unsubscribed_at", "created_at"]


class NotificationAdmin(admin.ModelAdmin):
    list_display = ["title", "recipient", "event", "is_read", "created_at"]
    list_filter = ["event", "is_read"]
    raw_id_fields = ["recipient"]
    search_fields = ["title", "recipient__username"]


class WebhookDeliveryInline(admin.TabularInline):
    model = models.WebhookDelivery
    extra = 0
    can_delete = False
    fields = ["event", "status", "attempts", "response_status", "last_error", "created_at"]
    readonly_fields = fields
    ordering = ["-created_at"]

    def has_add_permission(self, request, obj=None):
        return False


class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ["name", "url", "is_active"]
    list_filter = ["is_active"]
    inlines = [WebhookDeliveryInline]


class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ["event", "endpoint", "status", "attempts", "response_status", "created_at"]
    list_filter = ["status", "event"]
    readonly_fields = ["endpoint", "event", "event_id", "payload", "status", "attempts", "response_status", "last_error", "delivered_at"]
    actions = ["redeliver"]

    @admin.action(description=_("Retry selected deliveries"))
    def redeliver(self, request, queryset):
        from flex_blog.tasks import deliver_webhook, enqueue

        for pk in queryset.exclude(status=models.WebhookDelivery.Status.SUCCESS).values_list("pk", flat=True):
            enqueue(deliver_webhook, str(pk))


def register(site=admin.site):
    feature = blog_settings.feature_enabled
    registry = [
        (models.Article, ArticleAdmin, True),
        (models.Author, AuthorAdmin, True),
        (models.Category, CategoryAdmin, True),
        (models.Tag, TagAdmin, True),
        (models.Series, SeriesAdmin, True),  # always: articles autocomplete needs it
        (models.Comment, CommentAdmin, feature("comments")),
        (models.Media, MediaAdmin, feature("media")),
        (models.Subscriber, SubscriberAdmin, feature("newsletter")),
        (models.Notification, NotificationAdmin, feature("notifications")),
        (models.WebhookEndpoint, WebhookEndpointAdmin, feature("webhooks")),
        (models.WebhookDelivery, WebhookDeliveryAdmin, feature("webhooks")),
    ]
    for model, admin_class, enabled in registry:
        if enabled and not site.is_registered(model):
            site.register(model, admin_class)


if blog_settings.feature_enabled("admin"):
    register()

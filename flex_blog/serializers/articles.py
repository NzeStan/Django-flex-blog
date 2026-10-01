import json

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from flex_blog import permissions as perms
from flex_blog.api import Conflict, resolve_serializer
from flex_blog.conf import blog_settings
from flex_blog.models import Article, ArticleRevision, Author, Category, Series
from flex_blog.serializers.taxonomy import (
    AuthorSummarySerializer,
    CategorySummarySerializer,
    SeriesSummarySerializer,
    TagSummarySerializer,
)


def _user(serializer):
    request = serializer.context.get("request")
    return getattr(request, "user", None)


class ArticleListSerializer(serializers.ModelSerializer):
    override_name = "article_list"

    author = AuthorSummarySerializer(read_only=True)
    categories = CategorySummarySerializer(many=True, read_only=True)
    tags = TagSummarySerializer(many=True, read_only=True)
    series = SeriesSummarySerializer(read_only=True)
    url = serializers.CharField(source="get_absolute_url", read_only=True)
    is_locked = serializers.SerializerMethodField(help_text="True when members-only content is hidden from this reader.")

    class Meta:
        model = Article
        fields = [
            "id", "slug", "title", "subtitle", "excerpt", "cover_image", "cover_image_alt",
            "author", "categories", "tags", "series", "series_order",
            "status", "visibility", "language", "is_featured", "is_pinned",
            "published_at", "updated_at", "reading_time", "word_count",
            "views_count", "comment_count", "reaction_count", "url", "is_locked",
        ]
        read_only_fields = fields

    def get_is_locked(self, obj):
        return not perms.can_read_full_content(_user(self), obj)


class ArticleDetailSerializer(ArticleListSerializer):
    override_name = "article_detail"

    content = serializers.SerializerMethodField(help_text="Raw source; only returned to people who can edit the article.")
    content_html = serializers.SerializerMethodField()
    table_of_contents = serializers.SerializerMethodField()
    comments_open = serializers.SerializerMethodField()
    is_scheduled = serializers.BooleanField(read_only=True)
    reactions = serializers.SerializerMethodField()
    viewer = serializers.SerializerMethodField()
    series_navigation = serializers.SerializerMethodField()

    class Meta(ArticleListSerializer.Meta):
        fields = ArticleListSerializer.Meta.fields + [
            "content_format", "content", "content_html", "table_of_contents",
            "meta_title", "meta_description", "canonical_url", "noindex",
            "allow_comments", "comments_open", "is_scheduled", "version",
            "reactions", "viewer", "series_navigation", "extra_data", "created_at",
        ]
        read_only_fields = fields

    def _can_edit(self, obj):
        if not hasattr(self, "_edit_cache"):
            self._edit_cache = {}
        if obj.pk not in self._edit_cache:
            self._edit_cache[obj.pk] = perms.can_edit_article(_user(self), obj)
        return self._edit_cache[obj.pk]

    def get_content(self, obj):
        return obj.content if self._can_edit(obj) else None

    def get_content_html(self, obj):
        return obj.content_html if perms.can_read_full_content(_user(self), obj) else ""

    def get_table_of_contents(self, obj):
        return obj.table_of_contents if perms.can_read_full_content(_user(self), obj) else []

    def get_comments_open(self, obj):
        from flex_blog.services.comments import comments_open

        return comments_open(obj)

    def get_reactions(self, obj):
        if not blog_settings.feature_enabled("reactions"):
            return {}
        from flex_blog.services.engagement import reaction_summary

        return reaction_summary(obj)

    def get_viewer(self, obj):
        user = _user(self)
        state = {"can_edit": self._can_edit(obj), "reactions": [], "bookmarked": False}
        if user is not None and user.is_authenticated:
            if blog_settings.feature_enabled("reactions"):
                state["reactions"] = list(obj.reactions.filter(user=user).values_list("kind", flat=True))
            if blog_settings.feature_enabled("bookmarks"):
                state["bookmarked"] = obj.bookmarks.filter(user=user).exists()
        return state

    def get_series_navigation(self, obj):
        if not obj.series_id or not blog_settings.feature_enabled("series"):
            return None
        siblings = Article.objects.listed().filter(series_id=obj.series_id)
        previous = siblings.filter(series_order__lt=obj.series_order).order_by("-series_order").values("slug", "title").first()
        following = siblings.filter(series_order__gt=obj.series_order).order_by("series_order").values("slug", "title").first()
        return {"previous": previous, "next": following}


class ArticleWriteSerializer(serializers.ModelSerializer):
    """
    Create/update articles. Tags are given by name and created on the fly;
    categories and series by slug. Send ``version`` (from the last read) to
    get a 409 instead of silently overwriting someone else's edit.
    """

    override_name = "article_write"

    categories = serializers.SlugRelatedField(many=True, slug_field="slug", queryset=Category.objects.all(), required=False)
    tags = serializers.ListField(child=serializers.CharField(max_length=100), required=False, write_only=True)
    series = serializers.SlugRelatedField(slug_field="slug", queryset=Series.objects.all(), allow_null=True, required=False)
    author = serializers.SlugRelatedField(slug_field="slug", queryset=Author.objects.filter(is_active=True), required=False)
    version = serializers.IntegerField(required=False, write_only=True, min_value=1)

    editor_only_fields = ("is_featured", "is_pinned", "author")

    class Meta:
        model = Article
        fields = [
            "title", "subtitle", "slug", "summary", "content", "content_format",
            "categories", "tags", "series", "series_order", "cover_image", "cover_image_alt",
            "status", "visibility", "published_at", "is_featured", "is_pinned", "allow_comments",
            "language", "meta_title", "meta_description", "canonical_url", "noindex",
            "extra_data", "author", "version",
        ]
        extra_kwargs = {"slug": {"required": False}}

    def validate_content_format(self, value):
        if value not in blog_settings.ARTICLES["content_formats"]:
            raise serializers.ValidationError(_("This content format is not enabled."))
        return value

    def validate_tags(self, value):
        if len(value) > blog_settings.ARTICLES["max_tags"]:
            raise serializers.ValidationError(_("Too many tags."))
        return value

    def validate_categories(self, value):
        if len(value) > blog_settings.ARTICLES["max_categories"]:
            raise serializers.ValidationError(_("Too many categories."))
        return value

    def validate_extra_data(self, value):
        if not isinstance(value, dict) or len(json.dumps(value)) > 65536:
            raise serializers.ValidationError(_("Must be a JSON object under 64 KB."))
        return value

    def validate_language(self, value):
        from django.conf import settings

        codes = {code for code, _name in getattr(settings, "LANGUAGES", [])}
        if value and codes and value not in codes:
            raise serializers.ValidationError(_("Unsupported language."))
        return value

    def validate(self, attrs):
        user = _user(self)
        if not perms.is_editor(user):
            # Compare with the current value: multipart forms send unchecked
            # booleans as False, which must not count as "setting" them.
            def current(field):
                if self.instance is not None:
                    return getattr(self.instance, field)
                return None if field == "author" else False

            blocked = [f for f in self.editor_only_fields if f in attrs and attrs[f] != current(f)]
            if blocked:
                raise PermissionDenied(_("Only editors can set: %(fields)s.") % {"fields": ", ".join(blocked)})
        instance = self.instance
        status = attrs.get("status", instance.status if instance else Article.Status.DRAFT)
        becomes_published = status == Article.Status.PUBLISHED and (
            instance is None
            or instance.status != Article.Status.PUBLISHED
            or ("published_at" in attrs and attrs["published_at"] != instance.published_at)
        )
        if becomes_published and not perms.can_publish(user):
            raise PermissionDenied(_("You do not have permission to publish. Submit the article for review instead."))
        leaves_published = instance is not None and instance.status == Article.Status.PUBLISHED and status != Article.Status.PUBLISHED
        if leaves_published and not perms.can_publish(user):
            raise PermissionDenied(_("You do not have permission to unpublish."))
        return attrs

    def _apply_relations(self, article, categories, tags, user):
        if categories is not None:
            article.categories.set(categories)
        if tags is not None:
            from flex_blog.services.articles import set_tags

            set_tags(article, tags)

    def create(self, validated_data):
        user = _user(self)
        categories = validated_data.pop("categories", None)
        tags = validated_data.pop("tags", None)
        validated_data.pop("version", None)
        author = validated_data.pop("author", None)
        if author is None:
            if blog_settings.ARTICLES["auto_create_author_profile"]:
                author = Author.for_user(user)
            else:
                author = Author.objects.filter(user=user).first()
                if author is None:
                    raise PermissionDenied(_("Create an author profile first."))
        with transaction.atomic():
            article = Article(author=author, **validated_data)
            article._editor = user
            article.save()
            self._apply_relations(article, categories, tags, user)
        return article

    def update(self, instance, validated_data):
        user = _user(self)
        categories = validated_data.pop("categories", None)
        tags = validated_data.pop("tags", None)
        expected = validated_data.pop("version", None)
        with transaction.atomic():
            current = Article.objects.select_for_update().only("pk", "version").get(pk=instance.pk)
            if expected is not None and expected != current.version:
                raise Conflict()
            for field, value in validated_data.items():
                setattr(instance, field, value)
            instance.version = current.version
            instance._editor = user
            instance.save()
            self._apply_relations(instance, categories, tags, user)
        return instance

    def to_representation(self, instance):
        instance = Article.objects.with_relations().get(pk=instance.pk)
        return resolve_serializer(ArticleDetailSerializer)(instance, context=self.context).data


class ArticleRevisionSerializer(serializers.ModelSerializer):
    editor = serializers.SerializerMethodField()

    class Meta:
        model = ArticleRevision
        fields = ["id", "version", "title", "subtitle", "summary", "content", "content_format", "editor", "created_at"]
        read_only_fields = fields

    def get_editor(self, obj):
        return obj.editor.get_username() if obj.editor_id else None

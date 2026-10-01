from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from flex_blog.models import Author, Category, Series, Tag


class AuthorSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ["id", "slug", "display_name", "avatar"]


class AuthorSerializer(serializers.ModelSerializer):
    override_name = "author"
    article_count = serializers.IntegerField(read_only=True, default=0)
    url = serializers.CharField(source="get_absolute_url", read_only=True)

    class Meta:
        model = Author
        fields = ["id", "slug", "display_name", "bio", "avatar", "website", "social_links", "article_count", "url", "created_at"]


class AuthorProfileSerializer(serializers.ModelSerializer):
    """The signed-in author editing their own profile."""

    override_name = "author_profile"

    class Meta:
        model = Author
        fields = ["id", "slug", "display_name", "bio", "avatar", "website", "social_links", "is_active", "created_at"]
        read_only_fields = ["id", "is_active", "created_at"]

    def validate_social_links(self, value):
        if not isinstance(value, dict) or len(value) > 20:
            raise serializers.ValidationError(_("Provide up to 20 name/URL pairs."))
        url = serializers.URLField()
        for name, link in value.items():
            if not isinstance(name, str) or len(name) > 50:
                raise serializers.ValidationError(_("Invalid network name."))
            url.run_validation(link)
        return value


class CategorySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "slug", "name"]


class CategorySerializer(serializers.ModelSerializer):
    override_name = "category"
    parent = serializers.SlugRelatedField(slug_field="slug", queryset=Category.objects.all(), allow_null=True, required=False)
    article_count = serializers.IntegerField(read_only=True, default=0)
    url = serializers.CharField(source="get_absolute_url", read_only=True)

    class Meta:
        model = Category
        fields = [
            "id", "name", "slug", "description", "parent", "order", "is_active",
            "meta_title", "meta_description", "extra_data", "article_count", "url",
        ]
        extra_kwargs = {"slug": {"required": False}}

    def validate(self, attrs):
        parent = attrs.get("parent")
        if self.instance is not None and parent is not None:
            node, seen = parent, set()
            while node is not None and node.pk not in seen:
                if node.pk == self.instance.pk:
                    raise serializers.ValidationError({"parent": _("A category cannot be its own ancestor.")})
                seen.add(node.pk)
                node = node.parent
        return attrs


class TagSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "slug", "name"]


class TagSerializer(serializers.ModelSerializer):
    override_name = "tag"
    article_count = serializers.IntegerField(read_only=True, default=0)
    url = serializers.CharField(source="get_absolute_url", read_only=True)

    class Meta:
        model = Tag
        fields = ["id", "name", "slug", "description", "article_count", "url"]
        extra_kwargs = {"slug": {"required": False}}


class SeriesSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Series
        fields = ["id", "slug", "title"]


class SeriesSerializer(serializers.ModelSerializer):
    override_name = "series"
    author = AuthorSummarySerializer(read_only=True)
    article_count = serializers.IntegerField(read_only=True, default=0)
    url = serializers.CharField(source="get_absolute_url", read_only=True)

    class Meta:
        model = Series
        fields = ["id", "title", "slug", "description", "author", "is_active", "extra_data", "article_count", "url"]
        extra_kwargs = {"slug": {"required": False}}

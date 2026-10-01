from rest_framework import serializers

from flex_blog.models import Bookmark, Media, Notification
from flex_blog.serializers.articles import ArticleListSerializer


class MediaSerializer(serializers.ModelSerializer):
    override_name = "media"
    url = serializers.SerializerMethodField()

    class Meta:
        model = Media
        fields = ["id", "file", "url", "title", "alt_text", "caption", "kind", "mime_type", "size", "width", "height", "extra_data", "created_at"]
        read_only_fields = ["id", "url", "kind", "mime_type", "size", "width", "height", "created_at"]

    def get_url(self, obj):
        request = self.context.get("request")
        return request.build_absolute_uri(obj.url) if request and obj.url else obj.url

    def update(self, instance, validated_data):
        validated_data.pop("file", None)  # files are immutable; upload a new one instead
        return super().update(instance, validated_data)


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "event", "title", "body", "url", "data", "is_read", "read_at", "created_at"]
        read_only_fields = fields


class BookmarkSerializer(serializers.ModelSerializer):
    article = ArticleListSerializer(read_only=True)

    class Meta:
        model = Bookmark
        fields = ["id", "article", "created_at"]
        read_only_fields = fields


class SubscribeSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    language = serializers.CharField(max_length=15, required=False, allow_blank=True, default="")
    source = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=500)


class ReactionSerializer(serializers.Serializer):
    kind = serializers.CharField(read_only=True)
    reacted = serializers.BooleanField(read_only=True)
    reaction_count = serializers.IntegerField(read_only=True)

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from flex_blog import permissions as perms
from flex_blog.conf import blog_settings
from flex_blog.models import Comment


class CommentSerializer(serializers.ModelSerializer):
    """Public view of a comment. Emails and IPs are only shown to moderators."""

    override_name = "comment"

    article = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    author = serializers.SerializerMethodField()
    content = serializers.SerializerMethodField(help_text="Raw text; only returned to its author and moderators.")
    content_html = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    is_edited = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id", "article", "parent", "depth", "author", "content", "content_html",
            "status", "is_removed", "is_edited", "can_edit", "created_at", "edited_at",
        ]
        read_only_fields = fields

    def _user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def get_author(self, obj):
        avatar = None
        author_profile = getattr(obj.user, "blog_author", None) if obj.user_id else None
        if author_profile is not None and author_profile.avatar:
            request = self.context.get("request")
            avatar = request.build_absolute_uri(author_profile.avatar.url) if request else author_profile.avatar.url
        data = {
            "name": str(obj.display_name),
            "url": "" if obj.user_id else obj.author_url,
            "avatar": avatar,
            "is_guest": obj.user_id is None,
            "is_article_author": bool(obj.user_id and obj.article.author_id and obj.article.author.user_id == obj.user_id),
            "author_slug": author_profile.slug if author_profile else None,
        }
        if perms.is_moderator(self._user()):
            data["email"] = obj.notify_email
            data["ip_address"] = obj.ip_address
        return data

    def _owns(self, obj):
        user = self._user()
        return bool(user and user.is_authenticated and obj.user_id == user.pk)

    def get_content(self, obj):
        if obj.is_removed:
            return None
        return obj.content if self._owns(obj) or perms.is_moderator(self._user()) else None

    def get_content_html(self, obj):
        return "" if obj.is_removed else obj.content_html

    def get_is_edited(self, obj):
        return obj.edited_at is not None

    def get_can_edit(self, obj):
        if perms.is_moderator(self._user()):
            return True
        if not self._owns(obj) or obj.is_removed:
            return False
        window = blog_settings.COMMENTS["edit_window_minutes"]
        return window is None or (timezone.now() - obj.created_at).total_seconds() < window * 60


class CommentCreateSerializer(serializers.Serializer):
    override_name = "comment_create"

    article = serializers.SlugField(required=False, help_text="Article slug (not needed on /articles/{slug}/comments/).")
    parent = serializers.UUIDField(required=False, allow_null=True)
    content = serializers.CharField(max_length=20000, trim_whitespace=True)
    author_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    author_email = serializers.EmailField(required=False, allow_blank=True, default="")
    author_url = serializers.URLField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        honeypot = blog_settings.COMMENTS["honeypot_field"]
        if honeypot and self.initial_data.get(honeypot):
            raise serializers.ValidationError(_("Your comment could not be accepted."))
        return attrs


class CommentUpdateSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=20000)


class FlagSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from flex_blog import permissions as perms
from flex_blog.api import BlogViewMixin, call_service, resolve_serializer
from flex_blog.filters import CommentFilter
from flex_blog.models import Article, Comment
from flex_blog.serializers import CommentSerializer, CommentUpdateSerializer, FlagSerializer
from flex_blog.services import comments as comment_service
from flex_blog.views.articles import create_comment


class CommentViewSet(
    BlogViewMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Comments across all articles (filter with ``?article=<slug>``,
    ``?parent=<id|none>``). Moderators also see pending/spam comments and can
    ``approve``, ``reject`` or mark ``spam``. Authors of a comment can edit it
    (PATCH, within the edit window) and remove it (DELETE).
    """

    required_feature = "comments"
    serializer_class = CommentSerializer
    permission_classes = [perms.CommentPermission]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = CommentFilter
    ordering_fields = ["created_at"]
    ordering = ["created_at"]
    throttle_scopes = {"create": "comments", "partial_update": "comments", "flag": "comments"}

    def get_queryset(self):
        user = self.request.user
        queryset = Comment.objects.visible_to(user).select_related("user__blog_author", "article__author")
        if not perms.is_moderator(user):
            queryset = queryset.filter(article__status=Article.Status.PUBLISHED, article__published_at__lte=timezone.now())
            if self.action == "list":
                # Don't reveal unlisted articles through the site-wide feed.
                queryset = queryset.exclude(article__visibility=Article.Visibility.UNLISTED)
        return queryset

    def get_permissions(self):
        if self.action == "flag":
            return [permissions.IsAuthenticated()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        slug = request.data.get("article")
        if not slug:
            raise ValidationError({"article": _("This field is required.")})
        article = Article.objects.readable_by(request.user).filter(slug=slug).first()
        if article is None:
            raise ValidationError({"article": _("Article not found.")})
        return create_comment(self, request, article)

    def partial_update(self, request, *args, **kwargs):
        comment = self.get_object()
        serializer = CommentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = call_service(comment_service.edit, comment, request.user, serializer.validated_data["content"])
        return Response(resolve_serializer(CommentSerializer)(comment, context=self.get_serializer_context()).data)

    def perform_destroy(self, instance):
        comment_service.remove(instance, self.request.user)

    def _moderate(self, request, new_status):
        comment = self.get_object()
        comment, _changed = comment_service.moderate(comment.pk, new_status, moderator=request.user)
        return Response(resolve_serializer(CommentSerializer)(comment, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._moderate(request, Comment.Status.APPROVED)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._moderate(request, Comment.Status.REJECTED)

    @action(detail=True, methods=["post"])
    def spam(self, request, pk=None):
        return self._moderate(request, Comment.Status.SPAM)

    @action(detail=True, methods=["post"])
    def flag(self, request, pk=None):
        """Report a comment. One flag per user; repeating is harmless."""
        comment = self.get_object()
        serializer = FlagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = comment_service.flag(comment, request.user, serializer.validated_data["reason"])
        return Response({"flagged": True, "created": created}, status=status.HTTP_200_OK)

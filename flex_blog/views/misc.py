from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import mixins, parsers, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from flex_blog import permissions as perms
from flex_blog.api import BlogViewMixin, call_service, resolve_serializer
from flex_blog.cache import cached_response
from flex_blog.conf import blog_settings
from flex_blog.models import Article, Author, Bookmark, Category, Media, Notification, Tag
from flex_blog.search import search_articles
from flex_blog.serializers import (
    ArticleListSerializer,
    AuthorSerializer,
    BookmarkSerializer,
    CategorySerializer,
    MediaSerializer,
    NotificationSerializer,
    SubscribeSerializer,
    TagSerializer,
    TokenSerializer,
)
from flex_blog.services import newsletter


class MediaViewSet(BlogViewMixin, viewsets.ModelViewSet):
    """Media library for authors. Upload with multipart ``file``."""

    required_feature = "media"
    serializer_class = MediaSerializer
    permission_classes = [perms.MediaPermission]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]
    throttle_scopes = {"create": "uploads"}
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = Media.objects.all()
        if not self.request.user.has_perm("flex_blog.change_media"):
            queryset = queryset.filter(uploaded_by=self.request.user)
        kind = self.request.query_params.get("kind")
        return queryset.filter(kind=kind) if kind else queryset

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)

    def perform_destroy(self, instance):
        file = instance.file
        instance.delete()
        # Remove the stored file only once the row is really gone.
        transaction.on_commit(lambda: file.delete(save=False))


class BookmarkViewSet(BlogViewMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """The signed-in reader's saved articles. Add/remove via ``/articles/{slug}/bookmark/``."""

    required_feature = "bookmarks"
    serializer_class = BookmarkSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Bookmark.objects.filter(user=self.request.user, article__in=Article.objects.published())
            .select_related("article__author", "article__series")
            .prefetch_related("article__categories", "article__tags")
        )


class NotificationViewSet(BlogViewMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """In-app notifications of the signed-in user. ``?unread=true`` to filter."""

    required_feature = "notifications"
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Notification.objects.filter(recipient=self.request.user)
        if self.request.query_params.get("unread") in ("1", "true", "yes"):
            queryset = queryset.filter(is_read=False)
        return queryset

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        return Response({"count": Notification.objects.filter(recipient=request.user, is_read=False).count()})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_object()
        if not notification.is_read:
            Notification.objects.filter(pk=notification.pk, is_read=False).update(is_read=True, read_at=timezone.now())
            notification.refresh_from_db()
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        updated = Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True, read_at=timezone.now())
        return Response({"updated": updated})


class NewsletterViewSet(BlogViewMixin, viewsets.GenericViewSet):
    """
    Double opt-in newsletter. Every endpoint is idempotent and
    ``subscribe`` answers the same whether or not the address is known.
    """

    required_feature = "newsletter"
    permission_classes = [permissions.AllowAny]
    throttle_scopes = {"subscribe": "newsletter", "confirm": "newsletter", "unsubscribe": "newsletter"}
    serializer_class = SubscribeSerializer

    @action(detail=False, methods=["post"])
    def subscribe(self, request):
        serializer = SubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        call_service(newsletter.subscribe, **serializer.validated_data)
        message = _("Check your inbox to confirm your subscription.") if blog_settings.NEWSLETTER["double_opt_in"] else _("You are subscribed.")
        return Response({"detail": message}, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"], serializer_class=TokenSerializer)
    def confirm(self, request):
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subscriber = call_service(newsletter.confirm, serializer.validated_data["token"])
        return Response({"detail": _("Subscription confirmed."), "email": subscriber.email})

    @action(detail=False, methods=["post"], serializer_class=TokenSerializer)
    def unsubscribe(self, request):
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        call_service(newsletter.unsubscribe, serializer.validated_data["token"])
        return Response({"detail": _("You have been unsubscribed.")})


class SearchView(BlogViewMixin, APIView):
    """
    One-box search across the blog: ``GET /search/?q=words``. Returns the top
    articles, categories, tags and authors. For paginated article results
    use ``/articles/?q=words``.
    """

    required_feature = "search"
    permission_classes = [permissions.AllowAny]
    read_throttle_scope = "search"

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()[:200]
        if len(query) < 2:
            return Response({"detail": _("Enter at least 2 characters.")}, status=status.HTTP_400_BAD_REQUEST)

        def build():
            context = {"request": request}
            articles = search_articles(Article.objects.listed().with_relations(), query)[:10]
            categories = Category.objects.filter(is_active=True, name__icontains=query)[:5]
            tags = Tag.objects.filter(name__icontains=query)[:5]
            authors = Author.objects.filter(is_active=True, display_name__icontains=query)[:5]
            return Response({
                "query": query,
                "articles": resolve_serializer(ArticleListSerializer)(articles, many=True, context=context).data,
                "categories": CategorySerializer(categories, many=True, context=context).data,
                "tags": TagSerializer(tags, many=True, context=context).data,
                "authors": AuthorSerializer(authors, many=True, context=context).data,
            })

        return cached_response(request, build)

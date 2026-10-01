from django.db.models import Count, Q
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from flex_blog import permissions as perms
from flex_blog.api import BlogViewMixin, resolve_serializer
from flex_blog.cache import cached_response
from flex_blog.conf import blog_settings
from flex_blog.filters import CategoryFilter
from flex_blog.models import Article, Author, Category, Series, Tag
from flex_blog.serializers import AuthorProfileSerializer, AuthorSerializer, CategorySerializer, SeriesSerializer, TagSerializer


def published_count(relation="articles"):
    """Count only live articles, so drafts never leak through counters."""
    return Count(
        relation,
        filter=Q(**{f"{relation}__status": Article.Status.PUBLISHED, f"{relation}__published_at__lte": timezone.now()})
        & ~Q(**{f"{relation}__visibility": Article.Visibility.UNLISTED}),
        distinct=True,
    )


class CachedReadMixin:
    def list(self, request, *args, **kwargs):
        return cached_response(request, lambda: super(CachedReadMixin, self).list(request, *args, **kwargs))

    def retrieve(self, request, *args, **kwargs):
        return cached_response(request, lambda: super(CachedReadMixin, self).retrieve(request, *args, **kwargs))


class AuthorViewSet(BlogViewMixin, CachedReadMixin, viewsets.ReadOnlyModelViewSet):
    """Public author profiles. ``/authors/me/`` lets an author edit their own."""

    lookup_field = "slug"
    lookup_value_regex = r"[^/]+"
    serializer_class = AuthorSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["display_name", "bio"]
    ordering_fields = ["display_name", "created_at", "article_count"]
    ordering = ["display_name"]

    def get_queryset(self):
        return Author.objects.filter(is_active=True).annotate(article_count=published_count())

    @action(detail=False, methods=["get", "patch"], url_path="me")
    def me(self, request):
        user = request.user
        if not user.is_authenticated:
            raise PermissionDenied()
        author = Author.objects.filter(user=user).first()
        if author is None:
            if not perms.can_author(user):
                raise NotFound()
            author = Author.for_user(user)
        if request.method == "GET":
            return Response(resolve_serializer(AuthorProfileSerializer)(author, context=self.get_serializer_context()).data)
        serializer = resolve_serializer(AuthorProfileSerializer)(author, data=request.data, partial=True, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class CategoryViewSet(BlogViewMixin, CachedReadMixin, viewsets.ModelViewSet):
    """Categories. ``/categories/tree/`` returns the whole hierarchy nested."""

    lookup_field = "slug"
    lookup_value_regex = r"[^/]+"
    serializer_class = CategorySerializer
    permission_classes = [perms.ModelPermissionOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = CategoryFilter
    search_fields = ["name", "description"]
    ordering_fields = ["name", "order", "article_count"]
    ordering = ["order", "name"]

    def get_queryset(self):
        queryset = Category.objects.select_related("parent").annotate(article_count=published_count())
        if not self.request.user.has_perm("flex_blog.change_category"):
            queryset = queryset.filter(is_active=True)
        return queryset

    @action(detail=False, methods=["get"])
    def tree(self, request):
        def build():
            rows = list(self.get_queryset().order_by("order", "name"))
            data = {c.pk: {**CategorySerializer(c, context=self.get_serializer_context()).data, "children": []} for c in rows}
            roots = []
            for category in rows:
                node = data[category.pk]
                if category.parent_id in data:
                    data[category.parent_id]["children"].append(node)
                else:
                    roots.append(node)
            return Response(roots)

        return cached_response(request, build)


class TagViewSet(BlogViewMixin, CachedReadMixin, viewsets.ModelViewSet):
    lookup_field = "slug"
    lookup_value_regex = r"[^/]+"
    serializer_class = TagSerializer
    permission_classes = [perms.ModelPermissionOrReadOnly]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "article_count", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        return Tag.objects.annotate(article_count=published_count())


class SeriesViewSet(BlogViewMixin, CachedReadMixin, viewsets.ModelViewSet):
    """Series. Their articles: ``/articles/?series=<slug>&ordering=series_order``."""

    lookup_field = "slug"
    lookup_value_regex = r"[^/]+"
    required_feature = "series"
    serializer_class = SeriesSerializer
    permission_classes = [perms.ModelPermissionOrReadOnly]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["title", "description"]
    ordering_fields = ["title", "created_at", "article_count"]
    ordering = ["title"]

    def get_queryset(self):
        queryset = Series.objects.select_related("author").annotate(article_count=published_count())
        if not self.request.user.has_perm("flex_blog.change_series"):
            queryset = queryset.filter(is_active=True)
        return queryset

    def perform_create(self, serializer):
        author = Author.objects.filter(user=self.request.user).first()
        serializer.save(author=author)


class StatsView(BlogViewMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Dashboard numbers for editors."""

    pagination_class = None

    def list(self, request, *args, **kwargs):
        if not perms.is_editor(request.user):
            raise PermissionDenied()
        from django.db.models import Sum

        from flex_blog.models import Comment, Subscriber

        def by_status(model):
            return dict(model.objects.order_by().values_list("status").annotate(n=Count("pk")))

        top = Article.objects.published().order_by("-views_count").values("slug", "title", "views_count")[:10]
        data = {
            "articles": by_status(Article),
            "scheduled": Article.objects.scheduled().count(),
            "views": Article.objects.aggregate(total=Sum("views_count"))["total"] or 0,
            "top_articles": list(top),
        }
        if blog_settings.feature_enabled("comments"):
            data["comments"] = by_status(Comment)
        if blog_settings.feature_enabled("newsletter"):
            data["subscribers"] = by_status(Subscriber)
        return Response(data, status=status.HTTP_200_OK)

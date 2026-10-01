from datetime import timedelta

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from flex_blog import permissions as perms
from flex_blog.api import BlogViewMixin, call_service, resolve_serializer
from flex_blog.cache import cached_response
from flex_blog.conf import blog_settings
from flex_blog.filters import ArticleFilter, CommentFilter
from flex_blog.models import Article, ArticleRevision, Comment, SlugRedirect
from flex_blog.search import search_articles
from flex_blog.serializers import (
    ArticleDetailSerializer,
    ArticleListSerializer,
    ArticleRevisionSerializer,
    ArticleWriteSerializer,
    CommentCreateSerializer,
    CommentSerializer,
)
from flex_blog.services import articles as article_service
from flex_blog.services import comments as comment_service
from flex_blog.services import engagement


class ArticleOrdering(OrderingFilter):
    """Search results keep their relevance order unless ``ordering`` is given."""

    def get_default_ordering(self, view):
        if view.request.query_params.get("q"):
            return None
        return super().get_default_ordering(view)


def _require_feature(name):
    if not blog_settings.feature_enabled(name):
        raise NotFound()


class ArticleViewSet(BlogViewMixin, viewsets.ModelViewSet):
    """
    Articles.

    Listing (``GET /articles/``) returns the public feed. Filters: ``category``,
    ``tag`` (comma separated), ``author``, ``series``, ``language``,
    ``is_featured``, ``year``, ``month``, ``published_after/before``; ``q`` for
    search; ``ordering`` (e.g. ``-views_count``). Authors pass ``scope=mine``
    for their own articles (any status), editors ``scope=all``.
    """

    lookup_field = "slug"
    lookup_value_regex = r"[^/]+"
    permission_classes = [perms.ArticlePermission]
    filter_backends = [DjangoFilterBackend, ArticleOrdering]
    filterset_class = ArticleFilter
    ordering_fields = ["published_at", "created_at", "updated_at", "title", "views_count", "comment_count", "reaction_count", "series_order"]
    ordering = ["-is_pinned", "-published_at", "-created_at"]
    throttle_scopes = {"react": "reactions", "bookmark": "reactions", "article_comments": "comments"}

    def get_permissions(self):
        if self.action in ("react", "bookmark"):
            return [permissions.IsAuthenticated()]
        if self.action == "article_comments":
            return [perms.CommentPermission()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return resolve_serializer(ArticleWriteSerializer)
        if self.action == "retrieve":
            return resolve_serializer(ArticleDetailSerializer)
        return resolve_serializer(ArticleListSerializer)

    def get_queryset(self):
        user = self.request.user
        queryset = Article.objects.with_relations()
        if self.action == "list":
            scope = self.request.query_params.get("scope")
            if scope == "mine":
                return queryset.owned_by(user)
            if scope == "all" and perms.is_editor(user):
                return queryset
            queryset = queryset.listed()
            query = self.request.query_params.get("q")
            if query and blog_settings.feature_enabled("search"):
                queryset = search_articles(queryset, query)
            return queryset
        return queryset.readable_by(user)

    # --- reading ----------------------------------------------------------------

    def list(self, request, *args, **kwargs):
        if request.query_params.get("scope"):
            return super().list(request, *args, **kwargs)
        return cached_response(request, lambda: super(ArticleViewSet, self).list(request, *args, **kwargs))

    def _redirect(self, slug):
        if not blog_settings.feature_enabled("slug_redirects"):
            return None
        redirect = SlugRedirect.objects.select_related("article").filter(old_slug=slug).first()
        if redirect is None:
            return None
        try:
            location = reverse("flex_blog:article-detail", kwargs={"slug": redirect.article.slug})
        except NoReverseMatch:  # pragma: no cover - URLs mounted without the namespace
            location = ""
        response = Response({"detail": _("This article has moved."), "slug": redirect.article.slug}, status=status.HTTP_301_MOVED_PERMANENTLY)
        if location:
            response["Location"] = self.request.build_absolute_uri(location)
        return response

    def retrieve(self, request, slug=None, **kwargs):
        token = request.query_params.get("preview")
        article = self.get_queryset().filter(slug=slug).first()
        if article is None and token and blog_settings.feature_enabled("preview_links"):
            candidate = Article.objects.with_relations().filter(slug=slug).first()
            if candidate is not None and article_service.check_preview_token(candidate, token):
                article = candidate
        if article is None:
            redirect = self._redirect(slug)
            if redirect is not None:
                return redirect
            raise Http404
        if not token:
            article_service.record_view(article, request)
        serializer_class = self.get_serializer_class()
        return cached_response(request, lambda: Response(serializer_class(article, context=self.get_serializer_context()).data))

    @action(detail=True, methods=["get"])
    def related(self, request, slug=None):
        article = self.get_object()
        serializer = resolve_serializer(ArticleListSerializer)
        return cached_response(
            request, lambda: Response(serializer(article_service.related(article), many=True, context=self.get_serializer_context()).data)
        )

    @action(detail=False, methods=["get"])
    def popular(self, request):
        """Most viewed articles published in the last ``days`` (default 30, max 365)."""
        try:
            days = min(max(int(request.query_params.get("days", 30)), 1), 365)
        except ValueError:
            raise ValidationError({"days": _("Must be a number.")})
        since = timezone.now() - timedelta(days=days)
        queryset = Article.objects.listed().with_relations().filter(published_at__gte=since).order_by("-views_count", "-published_at")
        return cached_response(request, lambda: self._paginated(queryset))

    @action(detail=False, methods=["get"])
    def archive(self, request):
        """Article counts per month: ``[{"year": 2025, "month": 3, "count": 7}, ...]``."""
        return cached_response(request, lambda: Response(article_service.archive_counts(Article.objects.listed())))

    def _paginated(self, queryset, serializer_class=None):
        serializer_class = serializer_class or resolve_serializer(ArticleListSerializer)
        page = self.paginate_queryset(queryset)
        context = self.get_serializer_context()
        if page is not None:
            return self.get_paginated_response(serializer_class(page, many=True, context=context).data)
        return Response(serializer_class(queryset, many=True, context=context).data)

    # --- workflow ---------------------------------------------------------------

    def _detail_response(self, article, code=status.HTTP_200_OK):
        article = Article.objects.with_relations().get(pk=article.pk)
        return Response(resolve_serializer(ArticleDetailSerializer)(article, context=self.get_serializer_context()).data, status=code)

    @action(detail=True, methods=["post"])
    def publish(self, request, slug=None):
        """Publish now, or schedule with ``{"published_at": "<future ISO date>"}``. Idempotent."""
        article = self.get_object()
        if not perms.can_publish(request.user):
            raise PermissionDenied(_("You do not have permission to publish."))
        when = None
        if request.data.get("published_at"):
            from rest_framework.fields import DateTimeField

            when = DateTimeField().to_internal_value(request.data["published_at"])
        article_service.publish(article, user=request.user, when=when)
        return self._detail_response(article)

    @action(detail=True, methods=["post"])
    def unpublish(self, request, slug=None):
        """Back to draft, or ``{"status": "archived"}`` to archive. Idempotent."""
        article = self.get_object()
        target = request.data.get("status", Article.Status.DRAFT)
        if target not in (Article.Status.DRAFT, Article.Status.ARCHIVED):
            raise ValidationError({"status": _("Must be draft or archived.")})
        if article.status == Article.Status.PUBLISHED and not perms.can_publish(request.user):
            raise PermissionDenied(_("You do not have permission to unpublish."))
        article_service.unpublish(article, user=request.user, status=target)
        return self._detail_response(article)

    @action(detail=True, methods=["post"])
    def submit(self, request, slug=None):
        """Submit a draft for editorial review. Idempotent."""
        article = self.get_object()
        if article.status == Article.Status.PUBLISHED:
            raise ValidationError({"status": _("The article is already published.")})
        article_service.unpublish(article, user=request.user, status=Article.Status.REVIEW)
        return self._detail_response(article)

    @action(detail=True, methods=["post"], url_path="preview-link")
    def preview_link(self, request, slug=None):
        """A signed link that shows this (unpublished) article to anyone who has it."""
        _require_feature("preview_links")
        article = self.get_object()
        token = article_service.make_preview_token(article)
        from flex_blog.urls_utils import frontend_url

        return Response({
            "token": token,
            "url": frontend_url("article_preview", absolute=True, slug=article.slug, token=token),
            "expires_in": blog_settings.ARTICLES["preview_link_max_age"],
        })

    @action(detail=True, methods=["get"])
    def revisions(self, request, slug=None):
        _require_feature("revisions")
        article = self.get_object()
        if not perms.can_edit_article(request.user, article):
            raise PermissionDenied()  # history contains unpublished text
        return self._paginated(article_service.revisions(article), ArticleRevisionSerializer)

    @action(detail=True, methods=["post"], url_path=r"revisions/(?P<revision_id>[0-9a-fA-F-]{36})/restore")
    def restore_revision(self, request, slug=None, revision_id=None):
        _require_feature("revisions")
        article = self.get_object()
        revision = get_object_or_404(ArticleRevision, pk=revision_id, article=article)
        article_service.restore_revision(article, revision, user=request.user)
        return self._detail_response(article)

    # --- engagement -------------------------------------------------------------

    def _live_object(self):
        article = self.get_object()
        if not article.is_live:
            raise NotFound()
        return article

    @action(detail=True, methods=["put", "delete"], url_path=r"reactions/(?P<kind>[\w-]{1,30})")
    def react(self, request, slug=None, kind=None):
        """``PUT`` adds a reaction, ``DELETE`` removes it. Both are idempotent."""
        _require_feature("reactions")
        article = self._live_object()
        if request.method == "PUT":
            call_service(engagement.add_reaction, article, request.user, kind)
        else:
            call_service(engagement.remove_reaction, article, request.user, kind)
        article.refresh_from_db(fields=["reaction_count"])
        return Response({
            "kind": kind,
            "reacted": request.method == "PUT",
            "reaction_count": article.reaction_count,
            "reactions": engagement.reaction_summary(article),
        })

    @action(detail=True, methods=["put", "delete"])
    def bookmark(self, request, slug=None):
        """``PUT`` saves the article for later, ``DELETE`` removes it. Idempotent."""
        _require_feature("bookmarks")
        article = self._live_object()
        if request.method == "PUT":
            engagement.add_bookmark(article, request.user)
        else:
            engagement.remove_bookmark(article, request.user)
        return Response({"bookmarked": request.method == "PUT"})

    @action(detail=True, methods=["get", "post"], url_path="comments")
    def article_comments(self, request, slug=None):
        """List this article's comments (flat, with ``parent`` and ``depth``) or post one."""
        _require_feature("comments")
        article = self.get_object()
        if request.method == "GET":
            queryset = (
                Comment.objects.visible_to(request.user).filter(article=article)
                .select_related("user__blog_author", "article__author").order_by("created_at")
            )
            queryset = CommentFilter(request.query_params, queryset=queryset, request=request).qs
            return self._paginated(queryset, resolve_serializer(CommentSerializer))
        return create_comment(self, request, article)


def create_comment(view, request, article):
    serializer = resolve_serializer(CommentCreateSerializer)(data=request.data, context=view.get_serializer_context())
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    parent = None
    if data.get("parent"):
        parent = Comment.objects.filter(pk=data["parent"], article=article).first()
        if parent is None:
            raise ValidationError({"parent": _("Comment not found on this article.")})
    comment = call_service(
        comment_service.create, article, user=request.user, content=data["content"], parent=parent,
        author_name=data.get("author_name", ""), author_email=data.get("author_email", ""),
        author_url=data.get("author_url", ""), request=request,
    )
    output = resolve_serializer(CommentSerializer)(comment, context=view.get_serializer_context()).data
    return Response(output, status=status.HTTP_201_CREATED)


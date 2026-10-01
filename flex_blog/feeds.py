"""RSS 2.0 and Atom feeds: latest articles, and per category / tag / author."""

from django.contrib.syndication.views import Feed
from django.shortcuts import get_object_or_404
from django.utils.feedgenerator import Atom1Feed

from flex_blog.conf import blog_settings
from flex_blog.models import Article, Author, Category, Tag
from flex_blog.urls_utils import absolute_url, frontend_url


class LatestArticlesFeed(Feed):
    def title(self, obj=None):
        name = blog_settings.SITE_NAME
        return f"{name}: {obj}" if obj is not None else name

    def description(self, obj=None):
        return blog_settings.FEEDS["description"] or self.title(obj)

    def link(self, obj=None):
        if obj is not None and hasattr(obj, "get_absolute_url"):
            return absolute_url(obj.get_absolute_url())
        return absolute_url("/")

    def get_queryset(self, obj=None):
        return Article.objects.listed().select_related("author").prefetch_related("categories", "tags")

    def items(self, obj=None):
        return self.get_queryset(obj).order_by("-published_at")[: blog_settings.FEEDS["items"]]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.excerpt

    def item_link(self, item):
        return frontend_url("article", absolute=True, slug=item.slug)

    def item_guid(self, item):
        return str(item.pk)

    item_guid_is_permalink = False

    def item_pubdate(self, item):
        return item.published_at

    def item_updateddate(self, item):
        return item.updated_at

    def item_author_name(self, item):
        return item.author.display_name if item.author_id else None

    def item_categories(self, item):
        return [c.name for c in item.categories.all()] + [t.name for t in item.tags.all()]


class LatestArticlesAtomFeed(LatestArticlesFeed):
    feed_type = Atom1Feed

    def subtitle(self, obj=None):
        return self.description(obj)


class CategoryFeed(LatestArticlesFeed):
    def get_object(self, request, slug):
        return get_object_or_404(Category, slug=slug, is_active=True)

    def get_queryset(self, obj=None):
        return super().get_queryset().filter(categories__in=obj.get_descendant_ids()).distinct()


class TagFeed(LatestArticlesFeed):
    def get_object(self, request, slug):
        return get_object_or_404(Tag, slug=slug)

    def get_queryset(self, obj=None):
        return super().get_queryset().filter(tags=obj)


class AuthorFeed(LatestArticlesFeed):
    def get_object(self, request, slug):
        return get_object_or_404(Author, slug=slug, is_active=True)

    def get_queryset(self, obj=None):
        return super().get_queryset().filter(author=obj)

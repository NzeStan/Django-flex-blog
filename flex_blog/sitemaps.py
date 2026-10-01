"""
Sitemaps for the public (frontend) URLs of articles, categories, tags and
authors.

``/sitemap.xml`` is served by flex_blog itself (no template app needed). If
you already use ``django.contrib.sitemaps``, merge ``flex_blog.sitemaps.sitemaps``
into your own dict instead.
"""

from urllib.parse import urlparse
from xml.sax.saxutils import escape

from django.contrib.sitemaps import Sitemap
from django.core.paginator import EmptyPage, PageNotAnInteger
from django.db.models import Max
from django.http import Http404, HttpResponse

from flex_blog.conf import blog_settings
from flex_blog.models import Article, Author, Category, Tag


class BlogSitemap(Sitemap):
    def get_domain(self, site=None):
        parsed = urlparse(blog_settings.SITE_URL)
        if parsed.netloc:
            return parsed.netloc
        return super().get_domain(site)

    def get_protocol(self, protocol=None):
        parsed = urlparse(blog_settings.SITE_URL)
        return parsed.scheme or super().get_protocol(protocol)

    def location(self, item):
        # Sitemap prepends protocol + domain itself, so keep only the path.
        parsed = urlparse(item.get_absolute_url())
        return parsed.path + (f"?{parsed.query}" if parsed.query else "")


class ArticleSitemap(BlogSitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Article.objects.listed().filter(noindex=False).only("slug", "updated_at").order_by("-published_at")

    def lastmod(self, item):
        return item.updated_at


class CategorySitemap(BlogSitemap):
    changefreq = "weekly"
    priority = 0.5

    def items(self):
        return Category.objects.filter(is_active=True).order_by("order", "name")

    def lastmod(self, item):
        return item.updated_at


class TagSitemap(BlogSitemap):
    changefreq = "weekly"
    priority = 0.3

    def items(self):
        return Tag.objects.filter(articles__in=Article.objects.listed()).distinct().order_by("name")


class AuthorSitemap(BlogSitemap):
    changefreq = "weekly"
    priority = 0.4

    def items(self):
        return Author.objects.filter(is_active=True).annotate(last=Max("articles__updated_at")).order_by("display_name")

    def lastmod(self, item):
        return item.last


sitemaps = {
    "articles": ArticleSitemap,
    "categories": CategorySitemap,
    "tags": TagSitemap,
    "authors": AuthorSitemap,
}


def sitemap_view(request):
    from django.contrib.sites.shortcuts import get_current_site

    site = get_current_site(request)
    page = request.GET.get("p", 1)
    urls = []
    for sitemap_class in sitemaps.values():
        sitemap = sitemap_class()
        try:
            urls.extend(sitemap.get_urls(page=page, site=site, protocol=request.scheme))
        except EmptyPage:
            continue
        except PageNotAnInteger:
            raise Http404("Invalid page")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in urls:
        lines.append("<url>")
        lines.append(f"<loc>{escape(url['location'])}</loc>")
        if url.get("lastmod"):
            lines.append(f"<lastmod>{url['lastmod'].date().isoformat() if hasattr(url['lastmod'], 'date') else url['lastmod']}</lastmod>")
        if url.get("changefreq"):
            lines.append(f"<changefreq>{url['changefreq']}</changefreq>")
        if url.get("priority"):
            lines.append(f"<priority>{url['priority']}</priority>")
        lines.append("</url>")
    lines.append("</urlset>")
    return HttpResponse("\n".join(lines), content_type="application/xml")

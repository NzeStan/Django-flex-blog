"""
Mount the whole blog API with one line::

    path("api/blog/", include("flex_blog.urls")),

Only enabled features get routes. Feeds and the sitemap live under the same
prefix (``feeds/rss/``, ``feeds/atom/``, ``sitemap.xml``).
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from flex_blog import views
from flex_blog.conf import blog_settings

app_name = "flex_blog"

on = blog_settings.feature_enabled

router = DefaultRouter()
router.register("articles", views.ArticleViewSet, basename="article")
router.register("authors", views.AuthorViewSet, basename="author")
router.register("categories", views.CategoryViewSet, basename="category")
router.register("tags", views.TagViewSet, basename="tag")
router.register("stats", views.StatsView, basename="stats")
if on("series"):
    router.register("series", views.SeriesViewSet, basename="series")
if on("comments"):
    router.register("comments", views.CommentViewSet, basename="comment")
if on("media"):
    router.register("media", views.MediaViewSet, basename="media")
if on("bookmarks"):
    router.register("bookmarks", views.BookmarkViewSet, basename="bookmark")
if on("notifications"):
    router.register("notifications", views.NotificationViewSet, basename="notification")
if on("newsletter"):
    router.register("newsletter", views.NewsletterViewSet, basename="newsletter")

urlpatterns = []

if on("search"):
    urlpatterns.append(path("search/", views.SearchView.as_view(), name="search"))

if on("feeds"):
    from flex_blog import feeds

    urlpatterns += [
        path("feeds/rss/", feeds.LatestArticlesFeed(), name="feed-rss"),
        path("feeds/atom/", feeds.LatestArticlesAtomFeed(), name="feed-atom"),
        path("feeds/category/<str:slug>/", feeds.CategoryFeed(), name="feed-category"),
        path("feeds/tag/<str:slug>/", feeds.TagFeed(), name="feed-tag"),
        path("feeds/author/<str:slug>/", feeds.AuthorFeed(), name="feed-author"),
    ]

if on("sitemaps"):
    from flex_blog.sitemaps import sitemap_view

    urlpatterns.append(path("sitemap.xml", sitemap_view, name="sitemap"))

urlpatterns.append(path("", include(router.urls)))

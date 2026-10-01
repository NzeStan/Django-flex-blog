"""
Settings for django-flex-blog.

All configuration lives in a single ``FLEX_BLOG`` dict in your Django settings.
Anything you leave out falls back to ``DEFAULTS`` below; nested dicts are deep
merged, so you only ever override the keys you care about::

    FLEX_BLOG = {
        "FEATURES": {"newsletter": False},
        "COMMENTS": {"allow_anonymous": True},
        "TASKS": {"backend": "celery"},
    }

Access settings through ``blog_settings``::

    from flex_blog.conf import blog_settings
    blog_settings.COMMENTS["max_depth"]
    blog_settings.feature_enabled("comments")
"""

import copy

from django.conf import settings as django_settings
from django.core.signals import setting_changed
from django.utils.module_loading import import_string

DEFAULTS = {
    # Every feature can be switched off. A disabled feature exposes no URLs, no
    # admin, and connects no signal receivers. Its tables still exist so that
    # migrations stay stable when you toggle features later.
    "FEATURES": {
        "comments": True,
        "reactions": True,
        "bookmarks": True,
        "series": True,
        "media": True,
        "newsletter": True,
        "notifications": True,
        "webhooks": True,
        "search": True,
        "feeds": True,
        "sitemaps": True,
        "revisions": True,
        "view_counting": True,
        "idempotency": True,
        "response_cache": True,
        "preview_links": True,
        "slug_redirects": True,
        "admin": True,
    },
    # Absolute base URL of the public site, used to build links in emails,
    # feeds and webhook payloads, e.g. "https://example.com".
    "SITE_URL": "",
    "SITE_NAME": "Blog",
    # Paths of the pages on your frontend. The API is headless, so the package
    # needs to know where a reader actually sees an article.
    "FRONTEND_URLS": {
        "article": "/blog/{slug}/",
        "category": "/blog/category/{slug}/",
        "tag": "/blog/tag/{slug}/",
        "author": "/blog/author/{slug}/",
        "series": "/blog/series/{slug}/",
        "article_preview": "/blog/preview/{slug}/?token={token}",
        "newsletter_confirm": "/newsletter/confirm/?token={token}",
        "newsletter_unsubscribe": "/newsletter/unsubscribe/?token={token}",
    },
    "ARTICLES": {
        "content_formats": ["markdown", "html", "plain"],
        "default_content_format": "markdown",
        "words_per_minute": 200,
        "excerpt_length": 300,
        "max_tags": 10,
        "max_categories": 5,
        # When True, publishing needs the ``flex_blog.publish_article``
        # permission (superusers always have it). When False, any author may
        # publish their own articles.
        "require_publish_permission": True,
        # Create an Author profile automatically the first time a user who is
        # allowed to write creates an article.
        "auto_create_author_profile": True,
        "slug_allow_unicode": False,
        "related_count": 5,
        "preview_link_max_age": 60 * 60 * 24 * 3,
    },
    # Allow-list used to sanitize every piece of rendered HTML (articles,
    # comments). Anything not listed here is stripped.
    "SANITIZER": {
        "tags": [
            "a", "abbr", "b", "blockquote", "br", "code", "del", "div", "em",
            "figcaption", "figure", "h1", "h2", "h3", "h4", "h5", "h6", "hr",
            "i", "img", "ins", "kbd", "li", "mark", "ol", "p", "pre", "s",
            "small", "span", "strong", "sub", "sup", "table", "tbody", "td",
            "tfoot", "th", "thead", "tr", "u", "ul",
        ],
        "attributes": {
            "*": ["class", "id", "title", "lang", "dir"],
            "a": ["href", "name", "target"],
            "img": ["src", "alt", "width", "height", "loading"],
            "td": ["colspan", "rowspan", "align"],
            "th": ["colspan", "rowspan", "align", "scope"],
            "ol": ["start", "type"],
            "code": ["class"],
        },
        "url_schemes": ["http", "https", "mailto"],
        "comment_tags": ["a", "b", "blockquote", "br", "code", "em", "i", "li", "ol", "p", "pre", "strong", "ul"],
    },
    "COMMENTS": {
        "allow_anonymous": False,
        # "none": publish immediately; "anonymous": hold anonymous comments;
        # "first_time": hold until a user has one approved comment;
        # "all": hold everything for moderation.
        "moderation": "first_time",
        "max_depth": 4,
        "min_length": 2,
        "max_length": 5000,
        "max_links": 3,
        "blocked_words": [],
        "edit_window_minutes": 15,
        # Close comments on articles older than this many days (None = never).
        "close_after_days": None,
        "store_ip_address": False,
        "honeypot_field": "website_hp",
        # Send an approved comment back to moderation after this many flags.
        "flag_threshold": 5,
        # Dotted path to ``callable(comment, request) -> bool`` returning True
        # for spam, e.g. an Akismet integration.
        "spam_checker": None,
        "markdown": True,
    },
    "REACTIONS": {
        "kinds": ["like"],
    },
    "VIEW_COUNTING": {
        # The same reader counts once per article in this many seconds.
        "dedupe_seconds": 60 * 30,
        # Send the counter UPDATE through the task backend instead of the
        # request (useful for very hot articles together with Celery).
        "async": False,
    },
    "NEWSLETTER": {
        "double_opt_in": True,
        "confirm_max_age": 60 * 60 * 24 * 3,
        "send_on_publish": True,
        "batch_size": 200,
        "from_email": None,
    },
    "NOTIFICATIONS": {
        "backends": [
            "flex_blog.notifications.backends.InAppBackend",
            "flex_blog.notifications.backends.EmailBackend",
        ],
        "events": {
            "comment_on_article": True,
            "comment_reply": True,
            "comment_approved": True,
            "comment_pending": True,
        },
        # Extra addresses notified when a comment waits for moderation.
        "moderator_emails": [],
        # Dotted path to ``callable(message) -> bool``. Return False to drop a
        # notification, e.g. to honour per-user preferences.
        "recipient_filter": None,
        "from_email": None,
    },
    "WEBHOOKS": {
        "timeout": 5,
        "max_retries": 5,
        "allow_http": False,
        "allow_private_hosts": False,
    },
    "TASKS": {
        # "sync" runs background work right after the transaction commits, in
        # the same process. "celery" sends it to your Celery workers.
        "backend": "sync",
        "queue": None,
    },
    "CACHE": {
        "alias": "default",
        "timeout": 60 * 5,
        "key_prefix": "flexblog",
    },
    "THROTTLE_RATES": {
        "comments": "10/min",
        "reactions": "60/min",
        "newsletter": "5/hour",
        "search": "60/min",
        "uploads": "30/hour",
        "write": "120/min",
    },
    "PAGINATION": {
        "page_size": 20,
        "max_page_size": 100,
    },
    "MEDIA": {
        # Name of an entry in Django's STORAGES; None uses the default storage.
        "storage": None,
        "upload_to": "flex_blog/%Y/%m/",
        "max_upload_size": 10 * 1024 * 1024,
        "allowed_extensions": ["jpg", "jpeg", "png", "gif", "webp", "avif", "pdf", "mp4", "mp3"],
        "max_image_pixels": 50_000_000,
    },
    "IDEMPOTENCY": {
        "header": "Idempotency-Key",
        "ttl_seconds": 60 * 60 * 24,
    },
    "SEARCH": {
        "backend": "flex_blog.search.DatabaseSearchBackend",
        # Used by PostgresSearchBackend.
        "config": "english",
    },
    "FEEDS": {
        "items": 20,
        "description": "",
    },
    # Swap any serializer by dotted path, e.g.
    # {"article_detail": "myapp.serializers.MyArticleSerializer"}.
    "SERIALIZERS": {},
    # Dotted path to ``callable(user, article) -> bool`` deciding whether a
    # reader may see members-only content (plug your paywall in here).
    "CONTENT_ACCESS_CHECK": None,
    # Dotted path to ``callable(user) -> bool`` deciding who may write
    # articles. Default: users holding ``flex_blog.add_article``.
    "CAN_AUTHOR": None,
}


def _deep_merge(base, override):
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class BlogSettings:
    """Lazy, cached view of ``settings.FLEX_BLOG`` merged over the defaults."""

    def __init__(self):
        self._data = None
        self._imports = {}

    @property
    def data(self):
        if self._data is None:
            self._data = _deep_merge(DEFAULTS, getattr(django_settings, "FLEX_BLOG", {}))
        return self._data

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self.data[name]
        except KeyError:
            raise AttributeError(f"Unknown FLEX_BLOG setting: {name}") from None

    def feature_enabled(self, name):
        return bool(self.data["FEATURES"].get(name, False))

    def import_from(self, dotted_path):
        """Import (and cache) an object referenced by a dotted path setting."""
        if not dotted_path:
            return None
        if not isinstance(dotted_path, str):
            return dotted_path
        if dotted_path not in self._imports:
            self._imports[dotted_path] = import_string(dotted_path)
        return self._imports[dotted_path]

    def reload(self):
        self._data = None
        self._imports = {}


blog_settings = BlogSettings()


def _reload(*, setting, **kwargs):
    if setting == "FLEX_BLOG":
        blog_settings.reload()


setting_changed.connect(_reload)

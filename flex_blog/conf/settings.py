from django.conf import settings as django_settings
import logging

logger = logging.getLogger(__name__)

DEFAULTS = {
    "USE_UUID": True,
    "BLOG_MODELS": {
        "article": "flex_blog.models.Article",
        "author": "flex_blog.models.Author",
        "category": "flex_blog.models.Category",
        "tag": "flex_blog.models.Tag",
        "comment": "flex_blog.models.Comment",
        "media": "flex_blog.models.Media",
    },
    "FEATURES": {
        "comments": True,
        "tags": True,
        "categories": True,
        "authors": True,
        "search": True,
        "related_articles": True,
        "featured_articles": True,
        "drafts": True,
        "revisions": False,
    },
    "AUTH": {
        "anonymous_comments": False,
        "comment_moderation": True,
        "default_author_model": "auth.User",
        "default_author_filter": {"is_staff": True},
    },
    "PAGINATION": {
        "page_size": 20,
        "max_page_size": 100,
    },
    "MEDIA": {
        "storage_backend": "django.core.files.storage.FileSystemStorage",
        "max_image_size": 5242880,  # 5MB
        "image_sizes": {
            "thumbnail": {"width": 150, "height": 150, "crop": True},
            "medium": {"width": 800, "height": 600, "crop": False},
            "large": {"width": 1600, "height": 1200, "crop": False},
        },
        "allowed_extensions": ["jpg", "jpeg", "png", "gif", "webp"],
    },
    "URL_PREFIX": "blog/api/",
    "ADMIN": {
        "list_per_page": 25,
        "show_article_preview": True,
        "advanced_filters": True,
    },
    "MARKDOWN": {
        "enabled": True,
        "extensions": ["tables", "fenced_code", "codehilite"],
    },
    "CACHE": {
        "enabled": True,
        "timeout": 60 * 15,  # 15 minutes
    },
    "SEARCH": {
        "backend": "flex_blog.search.backends.DatabaseSearchBackend",
        "fields": ["title", "content", "summary"],
    },
    "API": {
        "throttling": {
            "anon": "20/hour",
            "user": "100/hour",
        },
        "versioning": {
            "enabled": True,
            "default": "v1",
            "allowed": ["v1"],
        },
    },
    "LOGGING": {
        "level": "INFO",
        "handlers": ["console"],
    },
    "SITEMAP": {
        "enabled": True,
        "priority": 0.7,
        "changefreq": "weekly",
    },
}


class Settings:
    """Settings management class with property access."""
    
    def __getattr__(self, name):
        if name.isupper():
            # Get from user settings, fall back to defaults
            user_settings = getattr(django_settings, 'FLEX_BLOG', {})
            
            # For nested dictionaries, merge them
            if name in user_settings and name in DEFAULTS and isinstance(DEFAULTS[name], dict):
                result = DEFAULTS[name].copy()
                result.update(user_settings.get(name, {}))
                return result
            
            # For simple values, override completely
            if name in user_settings:
                return user_settings[name]
            elif name in DEFAULTS:
                return DEFAULTS[name]
                
        raise AttributeError(f"'Settings' object has no attribute '{name}'")

settings = Settings()
"""System checks: catch misconfiguration at startup (``manage.py check --deploy``)."""

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register

from flex_blog.conf import DEFAULTS, blog_settings


@register()
def check_settings(app_configs, **kwargs):
    errors = []
    user = getattr(settings, "FLEX_BLOG", {})
    if not isinstance(user, dict):
        return [Error("FLEX_BLOG must be a dict.", id="flex_blog.E001")]
    for key in user:
        if key not in DEFAULTS:
            errors.append(Warning(f"Unknown FLEX_BLOG setting '{key}'.", hint="Check for typos.", id="flex_blog.W001"))
    for feature in user.get("FEATURES", {}):
        if feature not in DEFAULTS["FEATURES"]:
            errors.append(Warning(f"Unknown FLEX_BLOG feature '{feature}'.", id="flex_blog.W002"))

    for app in ("rest_framework", "django_filters"):
        if app not in settings.INSTALLED_APPS:
            errors.append(Error(f"'{app}' must be in INSTALLED_APPS for flex_blog.", id="flex_blog.E002"))

    backend = blog_settings.TASKS["backend"]
    if backend not in ("sync", "celery"):
        errors.append(Error("FLEX_BLOG['TASKS']['backend'] must be 'sync' or 'celery'.", id="flex_blog.E003"))
    if backend == "celery":
        try:
            import celery  # noqa: F401
        except ImportError:
            errors.append(Error("TASKS backend is 'celery' but Celery is not installed.", hint="pip install django-flex-blog[celery]", id="flex_blog.E004"))

    for name, path in [("SEARCH backend", blog_settings.SEARCH["backend"]), ("CAN_AUTHOR", blog_settings.CAN_AUTHOR),
                       ("CONTENT_ACCESS_CHECK", blog_settings.CONTENT_ACCESS_CHECK),
                       ("COMMENTS spam_checker", blog_settings.COMMENTS["spam_checker"]),
                       ("NOTIFICATIONS recipient_filter", blog_settings.NOTIFICATIONS["recipient_filter"]),
                       *[("NOTIFICATIONS backend", p) for p in blog_settings.NOTIFICATIONS["backends"]],
                       *[(f"SERIALIZERS[{k}]", p) for k, p in blog_settings.SERIALIZERS.items()]]:
        if path:
            try:
                blog_settings.import_from(path)
            except ImportError as exc:
                errors.append(Error(f"FLEX_BLOG {name}: cannot import '{path}' ({exc}).", id="flex_blog.E005"))

    if blog_settings.COMMENTS["moderation"] not in ("none", "anonymous", "first_time", "all"):
        errors.append(Error("COMMENTS['moderation'] must be none, anonymous, first_time or all.", id="flex_blog.E006"))
    fmt = blog_settings.ARTICLES["default_content_format"]
    if fmt not in blog_settings.ARTICLES["content_formats"]:
        errors.append(Error("ARTICLES['default_content_format'] must be one of ARTICLES['content_formats'].", id="flex_blog.E007"))
    return errors


@register(Tags.security, deploy=True)
def check_deploy(app_configs, **kwargs):
    warnings = []
    backend = settings.CACHES.get(blog_settings.CACHE["alias"], {}).get("BACKEND", "")
    if backend.endswith(("LocMemCache", "DummyCache")):
        warnings.append(Warning(
            "flex_blog uses the cache for throttling, view de-duplication and response caching. "
            "A per-process cache does not work across several workers.",
            hint="Use Redis or Memcached in production.", id="flex_blog.W010",
        ))
    if not blog_settings.SITE_URL:
        warnings.append(Warning(
            "FLEX_BLOG['SITE_URL'] is empty, so links in emails and webhooks will be relative.",
            hint='Set it to your public site, e.g. "https://example.com".', id="flex_blog.W011",
        ))
    if blog_settings.WEBHOOKS["allow_http"] or blog_settings.WEBHOOKS["allow_private_hosts"]:
        warnings.append(Warning("Webhooks may target http or private hosts.", id="flex_blog.W012"))
    if blog_settings.TASKS["backend"] == "sync" and blog_settings.feature_enabled("newsletter"):
        warnings.append(Warning(
            "Newsletters are sent in-process (TASKS backend 'sync'). Large lists will slow down publishing requests.",
            hint="Use the 'celery' backend for big audiences.", id="flex_blog.W013",
        ))
    return warnings

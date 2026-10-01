"""
Anonymous response cache with generation-based invalidation.

Every cached entry's key embeds a global "generation" number. Any write to
blog content bumps the generation (see ``flex_blog.receivers``), which makes
every old entry unreachable at once, so there is no need to work out which
URLs a change affects. Old entries simply expire. Only anonymous GETs are
cached, so personalised data is never shared between users.
"""

import hashlib
import logging

from django.core.cache import caches

from flex_blog.conf import blog_settings

logger = logging.getLogger("flex_blog")


def _cache():
    return caches[blog_settings.CACHE["alias"]]


def _version_key():
    return f"{blog_settings.CACHE['key_prefix']}:generation"


def get_version():
    cache = _cache()
    version = cache.get(_version_key())
    if version is None:
        cache.add(_version_key(), 1, None)
        version = cache.get(_version_key()) or 1
    return version


def bump_version():
    cache = _cache()
    try:
        cache.incr(_version_key())
    except ValueError:  # key missing
        cache.add(_version_key(), 2, None)
    except Exception:
        logger.warning("flex_blog: could not invalidate the response cache", exc_info=True)


def is_cacheable(request):
    return (
        blog_settings.feature_enabled("response_cache")
        and request.method == "GET"
        and not request.user.is_authenticated
        and "preview" not in request.query_params
    )


def response_key(request):
    raw = "|".join([
        request.path,
        "&".join(sorted(f"{k}={v}" for k, values in request.query_params.lists() for v in values)),
        request.META.get("HTTP_ACCEPT", ""),
        request.META.get("HTTP_ACCEPT_LANGUAGE", ""),
        request.get_host(),
    ])
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"{blog_settings.CACHE['key_prefix']}:resp:{get_version()}:{digest}"


def cached_response(request, builder):
    """Return ``builder()``'s Response, served from cache for anonymous GETs."""
    from rest_framework.response import Response

    if not is_cacheable(request):
        return builder()
    try:
        key = response_key(request)
        data = _cache().get(key)
    except Exception:
        logger.warning("flex_blog: response cache unavailable", exc_info=True)
        return builder()
    if data is not None:
        response = Response(data)
        response["X-Cache"] = "HIT"
        return response
    response = builder()
    if response.status_code == 200:
        try:
            _cache().set(key, response.data, blog_settings.CACHE["timeout"])
        except Exception:
            logger.warning("flex_blog: could not store response in cache", exc_info=True)
    response["X-Cache"] = "MISS"
    return response

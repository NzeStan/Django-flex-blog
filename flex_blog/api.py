"""
Shared API plumbing: idempotency keys, throttling, pagination and the
``BlogViewMixin`` every flex_blog view inherits.
"""

import hashlib
import json
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.utils.encoders import JSONEncoder

from flex_blog.conf import blog_settings

# --- errors -------------------------------------------------------------------


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = _("The resource was modified by someone else. Reload and try again.")
    default_code = "conflict"


class IdempotencyKeyMismatch(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = _("This Idempotency-Key was already used with a different request.")
    default_code = "idempotency_key_mismatch"


class IdempotencyInProgress(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = _("A request with this Idempotency-Key is still being processed.")
    default_code = "idempotency_in_progress"


class _Replay(Exception):
    def __init__(self, record):
        self.record = record


# --- throttling ---------------------------------------------------------------


class BlogThrottle(SimpleRateThrottle):
    """Rate limit whose rate comes from FLEX_BLOG["THROTTLE_RATES"][scope]."""

    cache_format = "flexblog_throttle_%(scope)s_%(ident)s"

    def __init__(self, scope):
        self.scope = scope
        super().__init__()

    def get_rate(self):
        return blog_settings.THROTTLE_RATES.get(self.scope)

    def get_cache_key(self, request, view):
        if self.rate is None:
            return None
        ident = f"u{request.user.pk}" if request.user.is_authenticated else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


# --- pagination ---------------------------------------------------------------


class BlogPagination(PageNumberPagination):
    page_size_query_param = "page_size"

    @property
    def page_size(self):
        return blog_settings.PAGINATION["page_size"]

    @property
    def max_page_size(self):
        return blog_settings.PAGINATION["max_page_size"]


# --- idempotency --------------------------------------------------------------


def _jsonable(data):
    return json.loads(json.dumps(data, cls=JSONEncoder)) if data is not None else None


def _scope(request):
    if request.user.is_authenticated:
        return f"user:{request.user.pk}"
    from flex_blog.utils import client_ip

    return "anon:" + hashlib.sha256(client_ip(request).encode()).hexdigest()[:40]


def _fingerprint(request):
    django_request = request._request
    content_type = django_request.META.get("CONTENT_TYPE", "")
    digest = hashlib.sha256(f"{request.method}|{request.path}|{content_type}|".encode())
    if content_type.startswith("multipart/"):
        digest.update(django_request.META.get("CONTENT_LENGTH", "").encode())
    else:
        digest.update(django_request.body)
    return digest.hexdigest()


class IdempotencyMixin:
    """
    Honour the ``Idempotency-Key`` header on unsafe requests.

    The first request with a key runs normally and its response is stored.
    Repeats with the same key and body get the stored response back (with
    ``Idempotent-Replayed: true``) without running anything again; a repeat
    still in flight gets 409; the same key with a different body gets 422.
    The unique (scope, key) constraint makes this safe across processes.
    5xx responses are not stored, so those can be retried.
    """

    idempotent_methods = ("POST", "PUT", "PATCH", "DELETE")

    def initial(self, request, *args, **kwargs):
        self._idempotency_record = None
        feature = getattr(self, "required_feature", None)
        if feature and not blog_settings.feature_enabled(feature):
            from rest_framework.exceptions import NotFound

            raise NotFound()
        super().initial(request, *args, **kwargs)
        if not blog_settings.feature_enabled("idempotency") or request.method not in self.idempotent_methods:
            return
        key = request.headers.get(blog_settings.IDEMPOTENCY["header"])
        if not key:
            return
        if len(key) > 255:
            raise ValidationError({"detail": _("Idempotency-Key must be at most 255 characters.")})
        from flex_blog.models import IdempotencyRecord

        scope, fingerprint = _scope(request), _fingerprint(request)
        expiry = timezone.now() - timedelta(seconds=blog_settings.IDEMPOTENCY["ttl_seconds"])
        for _attempt in range(2):
            try:
                with transaction.atomic():
                    self._idempotency_record = IdempotencyRecord.objects.create(
                        scope=scope, key=key, method=request.method, path=request.path[:500], fingerprint=fingerprint,
                    )
                return
            except IntegrityError:
                record = IdempotencyRecord.objects.filter(scope=scope, key=key).first()
                if record is None:
                    continue
                if record.created_at <= expiry:
                    record.delete()
                    continue
                if record.fingerprint != fingerprint:
                    raise IdempotencyKeyMismatch()
                if record.status == IdempotencyRecord.Status.PROCESSING:
                    raise IdempotencyInProgress()
                raise _Replay(record)
        raise IdempotencyInProgress()

    def handle_exception(self, exc):
        if isinstance(exc, _Replay):
            response = Response(exc.record.response_body, status=exc.record.response_status)
            response["Idempotent-Replayed"] = "true"
            return response
        return super().handle_exception(exc)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        record = getattr(self, "_idempotency_record", None)
        if record is not None:
            self._idempotency_record = None
            if response.status_code >= 500 or response.status_code == 429:
                record.delete()
            else:
                record.status = record.Status.COMPLETED
                record.response_status = response.status_code
                record.response_body = _jsonable(getattr(response, "data", None))
                record.save(update_fields=["status", "response_status", "response_body", "updated_at"])
        return response


class BlogViewMixin(IdempotencyMixin):
    """
    Base for all flex_blog views: idempotency keys, pagination, and per-action
    throttles. ``throttle_scopes`` maps an action name to the THROTTLE_RATES
    scope used for its writes; other writes use the "write" scope.
    """

    pagination_class = BlogPagination
    throttle_scopes = {}
    # Scopes applied to every request, reads included (e.g. "search").
    read_throttle_scope = None

    def get_throttles(self):
        throttles = list(super().get_throttles())
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            scope = self.read_throttle_scope
        else:
            scope = self.throttle_scopes.get(getattr(self, "action", None), "write")
        if scope:
            throttles.append(BlogThrottle(scope))
        return throttles

    def get_serializer_class(self):
        return resolve_serializer(super().get_serializer_class())


def resolve_serializer(cls):
    """Let FLEX_BLOG["SERIALIZERS"] swap any serializer by its ``override_name``."""
    override = blog_settings.SERIALIZERS.get(getattr(cls, "override_name", None) or "")
    return blog_settings.import_from(override) if override else cls


def call_service(func, *args, **kwargs):
    """Run a service function, translating Django errors into API errors."""
    from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
    from django.core.exceptions import ValidationError as DjangoValidationError
    from rest_framework.exceptions import PermissionDenied

    try:
        return func(*args, **kwargs)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages})
    except DjangoPermissionDenied as exc:
        raise PermissionDenied(str(exc) or None)

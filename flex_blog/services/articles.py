import hashlib
import logging

from django.core import signing
from django.core.cache import caches
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from django.utils.text import slugify

from flex_blog.conf import blog_settings
from flex_blog.models import Article, ArticleRevision, Tag
from flex_blog.signals import emit

logger = logging.getLogger("flex_blog")

PREVIEW_SALT = "flex_blog.article.preview"


def announce(article_id):
    """
    Fire ``article_published`` once per article. The conditional UPDATE is the
    lock: when two workers race, exactly one sees ``updated == 1``.
    """
    now = timezone.now()
    updated = Article.objects.filter(
        pk=article_id, announced_at__isnull=True,
        status=Article.Status.PUBLISHED, published_at__lte=now,
    ).update(announced_at=now)
    if not updated:
        return False
    article = Article.objects.with_relations().get(pk=article_id)
    emit("article_published", sender=Article, article=article)
    return True


def announce_due():
    """Announce scheduled articles whose publication time has arrived."""
    ids = list(Article.objects.published().filter(announced_at__isnull=True).values_list("pk", flat=True)[:500])
    return sum(1 for pk in ids if announce(pk))


def emit_unpublished(article):
    emit("article_unpublished", sender=Article, article=article)


def publish(article, user=None, when=None):
    """Publish now (or at ``when``). Idempotent: publishing a published article is a no-op."""
    if article.status == Article.Status.PUBLISHED and (when is None or article.published_at == when):
        return article
    article.status = Article.Status.PUBLISHED
    if when is not None:
        article.published_at = when
    elif not article.published_at or article.published_at > timezone.now():
        article.published_at = timezone.now()
    article._editor = user
    article.save()
    return article


def unpublish(article, user=None, status=Article.Status.DRAFT):
    if article.status == status:
        return article
    article.status = status
    article._editor = user
    article.save()
    return article


def set_tags(article, names):
    """Attach tags by name, creating missing ones. Safe under concurrency."""
    tags = []
    for raw in names:
        name = " ".join(str(raw).split())[:100]
        if not name:
            continue
        slug = slugify(name, allow_unicode=blog_settings.ARTICLES["slug_allow_unicode"])[:255]
        lookup = Q(name__iexact=name) | (Q(slug=slug) if slug else Q())
        tag = Tag.objects.filter(lookup).first()
        if tag is None:
            try:
                with transaction.atomic():
                    tag = Tag.objects.create(name=name, slug=slug)
            except IntegrityError:  # created concurrently by another request
                tag = Tag.objects.filter(lookup).first()
                if tag is None:
                    raise
        if tag not in tags:
            tags.append(tag)
    article.tags.set(tags)
    return tags


def related(article, limit=None):
    """Published articles sharing the most tags and categories, newest first."""
    limit = limit or blog_settings.ARTICLES["related_count"]
    tag_ids = list(article.tags.values_list("pk", flat=True))
    category_ids = list(article.categories.values_list("pk", flat=True))
    if not tag_ids and not category_ids:
        return Article.objects.none()
    return (
        Article.objects.listed()
        .exclude(pk=article.pk)
        .filter(Q(tags__in=tag_ids) | Q(categories__in=category_ids))
        .annotate(
            score=Count("tags", filter=Q(tags__in=tag_ids), distinct=True) * 2
            + Count("categories", filter=Q(categories__in=category_ids), distinct=True)
        )
        .order_by("-score", "-published_at")
        .with_relations()[:limit]
    )


def restore_revision(article, revision, user=None):
    if revision.article_id != article.pk:
        raise ValueError("Revision belongs to another article.")
    for field in ("title", "subtitle", "summary", "content", "content_format"):
        setattr(article, field, getattr(revision, field))
    article._editor = user
    article.save()
    return article


def revisions(article):
    return ArticleRevision.objects.filter(article=article).select_related("editor")


def make_preview_token(article):
    return signing.dumps({"a": str(article.pk), "v": article.version}, salt=PREVIEW_SALT, compress=True)


def check_preview_token(article, token):
    try:
        data = signing.loads(token, salt=PREVIEW_SALT, max_age=blog_settings.ARTICLES["preview_link_max_age"])
    except signing.BadSignature:
        return False
    return data.get("a") == str(article.pk)


def _viewer_fingerprint(request):
    from flex_blog.utils import client_ip

    if request.user.is_authenticated:
        return f"u{request.user.pk}"
    raw = f"{client_ip(request)}|{request.META.get('HTTP_USER_AGENT', '')[:200]}"
    return "a" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def record_view(article, request):
    """
    Count a view at most once per reader per dedupe window. ``cache.add`` is
    atomic on every real cache backend, so concurrent requests can't
    double-count. The counter itself is a single ``UPDATE ... SET n = n + 1``.
    """
    if not blog_settings.feature_enabled("view_counting") or not article.is_live:
        return False
    conf = blog_settings.VIEW_COUNTING
    cache = caches[blog_settings.CACHE["alias"]]
    key = f"{blog_settings.CACHE['key_prefix']}:view:{article.pk}:{_viewer_fingerprint(request)}"
    try:
        fresh = cache.add(key, 1, conf["dedupe_seconds"])
    except Exception:  # the cache being down must never break reading
        logger.warning("flex_blog: cache unavailable for view dedupe", exc_info=True)
        fresh = True
    if not fresh:
        return False
    if conf["async"]:
        from flex_blog.tasks import enqueue, increment_views

        enqueue(increment_views, str(article.pk))
    else:
        Article.objects.filter(pk=article.pk).update(views_count=F("views_count") + 1)
    user = request.user if request.user.is_authenticated else None
    emit("article_viewed", sender=Article, article=article, user=user)
    return True


def archive_counts(queryset):
    """[{year, month, count}] for archive navigation."""
    from django.db.models.functions import ExtractMonth, ExtractYear

    return list(
        queryset.order_by()
        .annotate(year=ExtractYear("published_at"), month=ExtractMonth("published_at"))
        .values("year", "month")
        .annotate(count=Count("pk"))
        .order_by("-year", "-month")
    )

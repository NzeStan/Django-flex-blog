from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, F
from django.utils.translation import gettext as _

from flex_blog.conf import blog_settings
from flex_blog.models import Article, Bookmark, Reaction
from flex_blog.signals import emit


def _check_kind(kind):
    if kind not in blog_settings.REACTIONS["kinds"]:
        raise ValidationError({"kind": _("Unknown reaction.")})


def add_reaction(article, user, kind="like"):
    """Idempotent: reacting twice keeps one reaction. Returns (reaction, created)."""
    _check_kind(kind)
    try:
        with transaction.atomic():
            reaction = Reaction.objects.create(article=article, user=user, kind=kind)
            Article.objects.filter(pk=article.pk).update(reaction_count=F("reaction_count") + 1)
    except IntegrityError:
        return Reaction.objects.get(article=article, user=user, kind=kind), False
    emit("reaction_added", sender=Reaction, reaction=reaction)
    return reaction, True


def remove_reaction(article, user, kind="like"):
    """Idempotent: removing a reaction that isn't there is fine."""
    _check_kind(kind)
    with transaction.atomic():
        deleted, _info = Reaction.objects.filter(article=article, user=user, kind=kind).delete()
        if deleted:
            Article.objects.filter(pk=article.pk, reaction_count__gt=0).update(reaction_count=F("reaction_count") - 1)
    if deleted:
        emit("reaction_removed", sender=Reaction, article=article, user=user, kind=kind)
    return bool(deleted)


def reaction_summary(article):
    return dict(Reaction.objects.filter(article=article).values_list("kind").annotate(n=Count("pk")).order_by())


def add_bookmark(article, user):
    bookmark, created = Bookmark.objects.get_or_create(article=article, user=user)
    if created:
        emit("bookmark_added", sender=Bookmark, bookmark=bookmark)
    return bookmark, created


def remove_bookmark(article, user):
    deleted, _info = Bookmark.objects.filter(article=article, user=user).delete()
    return bool(deleted)

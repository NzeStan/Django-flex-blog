from django.core.management.base import BaseCommand
from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import Coalesce

from flex_blog.models import Article, Comment, Reaction


def _count(model, filters):
    return Coalesce(
        Subquery(
            model.objects.filter(article=OuterRef("pk"), **filters)
            .order_by().values("article").annotate(n=Count("pk")).values("n")[:1]
        ),
        0,
    )


class Command(BaseCommand):
    help = "Recalculate the denormalised comment and reaction counters of every article."

    def handle(self, *args, **options):
        updated = Article.objects.update(
            comment_count=_count(Comment, {"status": Comment.Status.APPROVED, "is_removed": False}),
            reaction_count=_count(Reaction, {}),
        )
        self.stdout.write(self.style.SUCCESS(f"Recounted {updated} articles."))

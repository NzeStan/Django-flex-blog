import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_datetime

from flex_blog.models import Article, Author, Category, Comment, Series, Tag


def _dt(value):
    return parse_datetime(value) if isinstance(value, str) else value


def import_data(data):
    """
    Idempotent import: rows are matched by slug (comments by id) and updated
    in place, so running it twice gives the same result. Returns counts.
    Imported articles are marked as already announced, so importing never
    emails subscribers or fires ``article_published``.
    """
    if not isinstance(data, dict) or data.get("format") != "flex_blog":
        raise ValueError("Not a flex_blog export file.")
    User = get_user_model()
    users = {}

    def user(name):
        if not name:
            return None
        if name not in users:
            users[name] = User._default_manager.filter(**{User.USERNAME_FIELD: name}).first()
        return users[name]

    counts = {}
    with transaction.atomic():
        imported_authors = 0
        for row in data.get("authors", []):
            row = dict(row)
            owner = user(row.pop("user", None))
            if owner is None:
                continue
            slug = row.pop("slug")
            author = Author.objects.filter(user=owner).first() or Author(user=owner, slug=slug)
            for key, value in row.items():
                setattr(author, key, value)
            author.save()
            imported_authors += 1
        counts["authors"] = imported_authors

        parents = {}
        for row in data.get("categories", []):
            row = dict(row)
            slug = row.pop("slug")
            parents[slug] = row.pop("parent", None)
            Category.objects.update_or_create(slug=slug, defaults=row)
        for slug, parent in parents.items():
            Category.objects.filter(slug=slug).update(parent=Category.objects.filter(slug=parent).first() if parent else None)
        counts["categories"] = len(parents)

        for row in data.get("tags", []):
            row = dict(row)
            Tag.objects.update_or_create(slug=row.pop("slug"), defaults=row)
        counts["tags"] = len(data.get("tags", []))

        for row in data.get("series", []):
            row = dict(row)
            author_slug = row.pop("author", None)
            row["author"] = Author.objects.filter(slug=author_slug).first() if author_slug else None
            Series.objects.update_or_create(slug=row.pop("slug"), defaults=row)
        counts["series"] = len(data.get("series", []))

        for row in data.get("articles", []):
            row = dict(row)
            slug = row.pop("slug")
            categories, tags = row.pop("categories", []), row.pop("tags", [])
            author_slug, series_slug = row.pop("author", None), row.pop("series", None)
            row["published_at"] = _dt(row.get("published_at"))
            row["author"] = Author.objects.filter(slug=author_slug).first() if author_slug else None
            row["series"] = Series.objects.filter(slug=series_slug).first() if series_slug else None
            article = Article.objects.filter(slug=slug).first() or Article(slug=slug)
            for key, value in row.items():
                setattr(article, key, value)
            if article.status == Article.Status.PUBLISHED and not article.announced_at:
                article.announced_at = article.published_at
            article.save()
            article.categories.set(Category.objects.filter(slug__in=categories))
            article.tags.set(Tag.objects.filter(slug__in=tags))
        counts["articles"] = len(data.get("articles", []))

        imported_comments = 0
        for row in data.get("comments", []):
            row = dict(row)
            article = Article.objects.filter(slug=row.pop("article")).first()
            if article is None:
                continue
            parent_id = row.pop("parent", None)
            row["user"] = user(row.pop("user", None))
            row["article"] = article
            row["parent"] = Comment.objects.filter(pk=parent_id).first() if parent_id else None
            Comment.objects.update_or_create(pk=row.pop("id"), defaults=row)
            imported_comments += 1
        counts["comments"] = imported_comments
    return counts


class Command(BaseCommand):
    help = "Import a blog_export JSON file. Safe to re-run: existing rows are updated, not duplicated."

    def add_arguments(self, parser):
        parser.add_argument("path")

    def handle(self, *args, path, **options):
        try:
            with open(path, encoding="utf-8") as fh:
                counts = import_data(json.load(fh))
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc))
        call_command("blog_recount", stdout=self.stdout)
        for key, value in counts.items():
            self.stdout.write(f"{key}: {value}")
        self.stdout.write(self.style.SUCCESS("Import finished."))

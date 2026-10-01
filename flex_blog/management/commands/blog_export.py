import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.serializers.json import DjangoJSONEncoder

from flex_blog.models import Article, Author, Category, Comment, Series, Tag

FORMAT_VERSION = 1


def export_data(include_comments=True):
    """Everything as plain JSON, linked by slugs so it imports into any database."""
    username_field = get_user_model().USERNAME_FIELD
    data = {
        "format": "flex_blog",
        "version": FORMAT_VERSION,
        "authors": [
            {
                "slug": a.slug, "user": getattr(a.user, username_field), "display_name": a.display_name,
                "bio": a.bio, "website": a.website, "social_links": a.social_links, "is_active": a.is_active,
                "extra_data": a.extra_data,
            }
            for a in Author.objects.select_related("user").order_by("slug")
        ],
        "categories": [
            {
                "slug": c.slug, "name": c.name, "description": c.description,
                "parent": c.parent.slug if c.parent_id else None, "order": c.order, "is_active": c.is_active,
                "meta_title": c.meta_title, "meta_description": c.meta_description, "extra_data": c.extra_data,
            }
            for c in Category.objects.select_related("parent").order_by("slug")
        ],
        "tags": [{"slug": t.slug, "name": t.name, "description": t.description} for t in Tag.objects.order_by("slug")],
        "series": [
            {
                "slug": s.slug, "title": s.title, "description": s.description,
                "author": s.author.slug if s.author_id else None, "is_active": s.is_active, "extra_data": s.extra_data,
            }
            for s in Series.objects.select_related("author").order_by("slug")
        ],
        "articles": [
            {
                "slug": a.slug, "title": a.title, "subtitle": a.subtitle, "summary": a.summary, "content": a.content,
                "content_format": a.content_format, "author": a.author.slug if a.author_id else None,
                "categories": [c.slug for c in a.categories.all()], "tags": [t.slug for t in a.tags.all()],
                "series": a.series.slug if a.series_id else None, "series_order": a.series_order,
                "cover_image": a.cover_image.name or "", "cover_image_alt": a.cover_image_alt,
                "status": a.status, "visibility": a.visibility, "published_at": a.published_at,
                "is_featured": a.is_featured, "is_pinned": a.is_pinned, "allow_comments": a.allow_comments,
                "language": a.language, "meta_title": a.meta_title, "meta_description": a.meta_description,
                "canonical_url": a.canonical_url, "noindex": a.noindex, "extra_data": a.extra_data,
            }
            for a in Article.objects.select_related("author", "series").prefetch_related("categories", "tags").order_by("created_at")
        ],
    }
    if include_comments:
        data["comments"] = [
            {
                "id": str(c.pk), "article": c.article.slug, "parent": str(c.parent_id) if c.parent_id else None,
                "user": getattr(c.user, username_field) if c.user_id else None, "author_name": c.author_name,
                "author_email": c.author_email, "author_url": c.author_url, "content": c.content,
                "status": c.status, "is_removed": c.is_removed,
            }
            for c in Comment.objects.select_related("article", "user").order_by("depth", "created_at")
        ]
    return data


class Command(BaseCommand):
    help = "Export all blog content to JSON (a file or stdout) that blog_import can read back."

    def add_arguments(self, parser):
        parser.add_argument("--output", "-o", default="-", help="File path, or - for stdout (default).")
        parser.add_argument("--no-comments", action="store_true", help="Leave comments out (they contain emails).")

    def handle(self, *args, output, no_comments, **options):
        payload = json.dumps(export_data(include_comments=not no_comments), cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)
        if output == "-":
            self.stdout.write(payload)
        else:
            with open(output, "w", encoding="utf-8") as fh:
                fh.write(payload)
            self.stderr.write(self.style.SUCCESS(f"Exported to {output}"))

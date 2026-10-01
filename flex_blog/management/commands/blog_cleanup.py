from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from flex_blog.models import Article, Comment


class Command(BaseCommand):
    help = "Delete old spam/rejected comments and, only if you ask for it, stale drafts."

    def add_arguments(self, parser):
        parser.add_argument("--spam-days", type=int, default=30, help="Delete spam/rejected comments older than this (default 30).")
        parser.add_argument("--drafts-days", type=int, default=None, help="Also delete drafts untouched for this many days (off by default).")
        parser.add_argument("--dry-run", action="store_true", help="Only report what would be deleted.")

    def handle(self, *args, spam_days, drafts_days, dry_run, **options):
        now = timezone.now()
        comments = Comment.objects.filter(
            status__in=[Comment.Status.SPAM, Comment.Status.REJECTED], updated_at__lt=now - timedelta(days=spam_days),
        )
        drafts = Article.objects.none()
        if drafts_days is not None:
            drafts = Article.objects.filter(status=Article.Status.DRAFT, updated_at__lt=now - timedelta(days=drafts_days))
        self.stdout.write(f"Comments to delete: {comments.count()}; drafts to delete: {drafts.count()}")
        if dry_run:
            self.stdout.write("Dry run: nothing deleted.")
            return
        deleted_comments = comments.delete()[0]
        deleted_drafts = drafts.delete()[0]
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted_comments} comment rows and {deleted_drafts} draft rows."))

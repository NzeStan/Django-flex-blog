from django.core.management.base import BaseCommand
from django.utils.translation import gettext_lazy as _
from flex_blog.registry import model_registry
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = _('Clean up old draft articles and unapproved comments')
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help=_('Number of days to keep drafts (default: 30)')
        )
        parser.add_argument(
            '--comment-days',
            type=int,
            default=7,
            help=_('Number of days to keep unapproved comments (default: 7)')
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help=_('Perform a dry run without deleting anything')
        )
    
    def handle(self, *args, **options):
        """Handle the command execution."""
        days = options['days']
        comment_days = options['comment_days']
        dry_run = options['dry_run']
        
        # Get models
        Article = model_registry.get_model('article')
        Comment = model_registry.get_model('comment')
        
        # Calculate cutoff dates
        article_cutoff = timezone.now() - timedelta(days=days)
        comment_cutoff = timezone.now() - timedelta(days=comment_days)
        
        # Find old draft articles
        old_drafts = Article.objects.filter(
            status='draft',
            updated_at__lt=article_cutoff
        )
        
        # Find old unapproved comments
        old_comments = Comment.objects.filter(
            is_approved=False,
            created_at__lt=comment_cutoff
        )
        
        # Report what will be deleted
        self.stdout.write(self.style.WARNING(
            _('Found {0} old draft articles and {1} unapproved comments.').format(
                old_drafts.count(), old_comments.count()
            )
        ))
        
        # Exit if dry run
        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                _('Dry run completed. No records were deleted.')
            ))
            return
            
        # Delete the records
        drafts_deleted = old_drafts.delete()[0]
        comments_deleted = old_comments.delete()[0]
        
        # Log the deletions
        logger.info(f'Deleted {drafts_deleted} old draft articles')
        logger.info(f'Deleted {comments_deleted} unapproved comments')
        
        # Report success
        self.stdout.write(self.style.SUCCESS(
            _('Successfully deleted {0} old draft articles and {1} unapproved comments.').format(
                drafts_deleted, comments_deleted
            )
        ))
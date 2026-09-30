from django.db import models
from django.utils.translation import gettext_lazy as _
from flex_blog.models.base import FlexBaseModel
from django.conf import settings as django_settings
from mptt.models import MPTTModel, TreeForeignKey


class Comment(MPTTModel, FlexBaseModel):
    """Comment model for blog articles."""
    
    article = models.ForeignKey(
        'flex_blog.Article',
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name=_('Article')
    )
    
    author_name = models.CharField(
        max_length=255,
        verbose_name=_('Author Name'),
        help_text=_('Name of the comment author')
    )
    
    author_email = models.EmailField(
        verbose_name=_('Author Email'),
        blank=True,
        help_text=_('Email of the comment author')
    )
    
    author_website = models.URLField(
        blank=True,
        verbose_name=_('Author Website')
    )
    
    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blog_comments',
        verbose_name=_('User')
    )
    
    content = models.TextField(
        verbose_name=_('Content')
    )
    
    parent = TreeForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name=_('Parent Comment')
    )
    
    is_approved = models.BooleanField(
        default=False,
        verbose_name=_('Approved'),
        help_text=_('Whether the comment is approved')
    )
    
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_('IP Address')
    )
    
    user_agent = models.TextField(
        blank=True,
        verbose_name=_('User Agent')
    )
    
    class Meta:
        verbose_name = _('Comment')
        verbose_name_plural = _('Comments')
        ordering = ['-created_at']
    
    class MPTTMeta:
        order_insertion_by = ['-created_at']
    
    def __str__(self):
        return f"Comment by {self.author_name} on {self.article}"
    
    @property
    def is_from_authenticated_user(self):
        """Check if the comment is from an authenticated user."""
        return self.user is not None
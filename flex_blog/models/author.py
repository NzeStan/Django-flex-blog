from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings as django_settings
from flex_blog.models.base import FlexBaseModel
from flex_blog.conf import settings
from django.contrib.auth import get_user_model


class Author(FlexBaseModel):
    """Author model for blog articles."""
    
    user = models.OneToOneField(
        get_user_model(),
        on_delete=models.CASCADE,
        related_name='blog_author',
        verbose_name=_('User')
    )
    
    display_name = models.CharField(
        max_length=255,
        verbose_name=_('Display Name'),
        help_text=_('Name to display for the author')
    )
    
    bio = models.TextField(
        blank=True,
        verbose_name=_('Biography'),
        help_text=_('Author biography')
    )
    
    profile_image = models.ImageField(
        upload_to='blog/authors/',
        blank=True,
        null=True,
        verbose_name=_('Profile Image')
    )
    
    website = models.URLField(
        blank=True,
        verbose_name=_('Website')
    )
    
    social_links = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('Social Links'),
        help_text=_('Social media links as JSON')
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Active'),
        help_text=_('Whether the author is active')
    )
    
    class Meta:
        verbose_name = _('Author')
        verbose_name_plural = _('Authors')
        ordering = ['display_name']
    
    def __str__(self):
        return self.display_name
    
    @property
    def article_count(self):
        """Get the number of articles written by this author."""
        from flex_blog.registry import model_registry
        Article = model_registry.get_model('article')
        return Article.objects.filter(author=self).count()
    
    @property
    def latest_article(self):
        """Get the latest article written by this author."""
        from flex_blog.registry import model_registry
        Article = model_registry.get_model('article')
        return Article.objects.filter(
            author=self, 
            status='published'
        ).order_by('-published_at').first()
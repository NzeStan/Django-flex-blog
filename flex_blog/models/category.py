from django.db import models
from django.utils.translation import gettext_lazy as _
from flex_blog.models.base import SluggedModel
from mptt.models import MPTTModel, TreeForeignKey


class Category(MPTTModel, SluggedModel):
    """Category model for blog articles."""
    
    description = models.TextField(
        blank=True,
        verbose_name=_('Description')
    )
    
    parent = TreeForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name=_('Parent Category')
    )
    
    order = models.IntegerField(
        default=0,
        verbose_name=_('Order'),
        help_text=_('Order of display')
    )
    
    icon = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_('Icon'),
        help_text=_('CSS class for the icon')
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Active'),
        help_text=_('Whether the category is active')
    )
    
    class Meta:
        verbose_name = _('Category')
        verbose_name_plural = _('Categories')
        ordering = ['order', 'name']
    
    class MPTTMeta:
        order_insertion_by = ['name']
    
    @property
    def article_count(self):
        """Get the number of articles in this category."""
        from flex_blog.registry import model_registry
        Article = model_registry.get_model('article')
        return Article.objects.filter(
            categories=self, 
            status='published'
        ).count()
    
    def get_absolute_url(self):
        """Get the absolute URL of the category."""
        from django.urls import reverse
        return reverse('flex_blog:category-detail', kwargs={'slug': self.slug})

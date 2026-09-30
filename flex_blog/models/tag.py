from django.db import models
from django.utils.translation import gettext_lazy as _
from flex_blog.models.base import SluggedModel


class Tag(SluggedModel):
    """Tag model for blog articles."""
    
    description = models.TextField(
        blank=True,
        verbose_name=_('Description')
    )
    
    color = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_('Color'),
        help_text=_('Hex color code or color name')
    )
    
    class Meta:
        verbose_name = _('Tag')
        verbose_name_plural = _('Tags')
        ordering = ['name']
    
    @property
    def article_count(self):
        """Get the number of articles with this tag."""
        from flex_blog.registry import model_registry
        Article = model_registry.get_model('article')
        return Article.objects.filter(
            tags=self, 
            status='published'
        ).count()
    
    def get_absolute_url(self):
        """Get the absolute URL of the tag."""
        from django.urls import reverse
        return reverse('flex_blog:tag-detail', kwargs={'slug': self.slug})

from django.db import models
from django.utils.translation import gettext_lazy as _
import uuid
from flex_blog.conf import settings


class FlexBaseModel(models.Model):
    """Base model class for all blog models with flexible ID configuration."""
    
    # This is configurable via settings
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name=_('ID')
    ) if settings.USE_UUID else models.AutoField(
        primary_key=True, 
        verbose_name=_('ID')
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name=_('Created At')
    )
    updated_at = models.DateTimeField(
        auto_now=True, 
        verbose_name=_('Updated At')
    )
    extra_data = models.JSONField(
        default=dict, 
        blank=True, 
        verbose_name=_('Extra Data')
    )
    
    class Meta:
        abstract = True


class SluggedModel(FlexBaseModel):
    """Base model with slug field."""
    
    name = models.CharField(
        max_length=255, 
        verbose_name=_('Name')
    )
    slug = models.SlugField(
        max_length=255, 
        unique=True, 
        verbose_name=_('Slug'),
        help_text=_('URL-friendly version of the name')
    )
    
    class Meta:
        abstract = True
        
    def __str__(self):
        return self.name


class TimeStampedModel(FlexBaseModel):
    """Base model with created and updated timestamps."""
    
    class Meta:
        abstract = True
        ordering = ['-created_at']


class PublishableModel(TimeStampedModel):
    """Base model for publishable content."""
    
    STATUS_CHOICES = (
        ('draft', _('Draft')),
        ('published', _('Published')),
        ('archived', _('Archived')),
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name=_('Status')
    )
    published_at = models.DateTimeField(
        null=True, 
        blank=True, 
        verbose_name=_('Published At')
    )
    
    class Meta:
        abstract = True
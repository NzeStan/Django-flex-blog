from django.db import models
from django.utils.translation import gettext_lazy as _
from flex_blog.models.base import FlexBaseModel
from django.core.validators import FileExtensionValidator
from flex_blog.conf import settings
import os


class Media(FlexBaseModel):
    """Media model for blog articles."""
    
    title = models.CharField(
        max_length=255,
        verbose_name=_('Title')
    )
    
    file = models.FileField(
        upload_to='blog/media/%Y/%m/',
        verbose_name=_('File'),
        validators=[
            FileExtensionValidator(
                allowed_extensions=settings.MEDIA.get('allowed_extensions', 
                                                     ['jpg', 'jpeg', 'png', 'gif', 'webp'])
            )
        ]
    )
    
    description = models.TextField(
        blank=True,
        verbose_name=_('Description')
    )
    
    alt_text = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Alt Text'),
        help_text=_('Alternative text for accessibility')
    )
    
    type = models.CharField(
        max_length=50,
        editable=False,
        verbose_name=_('File Type')
    )
    
    size = models.PositiveIntegerField(
        editable=False,
        verbose_name=_('File Size'),
        help_text=_('Size in bytes')
    )
    
    class Meta:
        verbose_name = _('Media')
        verbose_name_plural = _('Media')
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        # Set file type based on extension
        _, ext = os.path.splitext(self.file.name)
        self.type = ext.lower()[1:]  # Remove the dot
        
        # Set file size
        if self.file and hasattr(self.file, 'size'):
            self.size = self.file.size
        
        super().save(*args, **kwargs)
    
    @property
    def url(self):
        """Get the URL of the file."""
        return self.file.url
    
    @property
    def filename(self):
        """Get the filename of the file."""
        return os.path.basename(self.file.name)
    
    @property
    def is_image(self):
        """Check if the file is an image."""
        return self.type.lower() in ['jpg', 'jpeg', 'png', 'gif', 'webp']
    
    def get_thumbnail_url(self):
        """Get the URL of the thumbnail."""
        # This is a placeholder - in a real implementation, you'd 
        # use a library like sorl-thumbnail or django-versatileimagefield
        # to generate and return a thumbnail URL
        if not self.is_image:
            return None
        return self.url
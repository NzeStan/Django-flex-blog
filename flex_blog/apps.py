from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FlexBlogConfig(AppConfig):
    name = 'flex_blog'
    verbose_name = _('Flex Blog')
    
    def ready(self):
        # Import signal handlers
        import flex_blog.signals  # noqa
        
        # Initialize the model registry
        from flex_blog.registry import model_registry
        model_registry.initialize()
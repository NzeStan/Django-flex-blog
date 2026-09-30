from django.apps import apps
from django.utils.module_loading import import_string
import logging

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Registry for dynamic model resolution."""
    
    def __init__(self):
        self._registry = {}
        self._initialized = False
    
    def initialize(self):
        """Initialize the registry with configured models."""
        if self._initialized:
            return
            
        from flex_blog.conf import settings
        
        for key, model_path in settings.BLOG_MODELS.items():
            try:
                if isinstance(model_path, str):
                    # Either direct model path or app.Model format
                    try:
                        model = import_string(model_path)
                    except ImportError:
                        # Try app.Model format
                        app_label, model_name = model_path.split('.')
                        model = apps.get_model(app_label, model_name)
                else:
                    # Already a model class
                    model = model_path
                
                self._registry[key] = model
            except Exception as e:
                logger.error(f"Failed to load model for {key}: {e}")
                
        self._initialized = True
    
    def get_model(self, key):
        """Get a model by key."""
        if not self._initialized:
            self.initialize()
        return self._registry.get(key)

    def get_all_models(self):
        """Get all registered models."""
        if not self._initialized:
            self.initialize()
        return self._registry

# Singleton instance
model_registry = ModelRegistry()
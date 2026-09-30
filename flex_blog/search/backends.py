from django.db.models import Q
from flex_blog.registry import model_registry
from flex_blog.conf import settings
import logging

logger = logging.getLogger(__name__)


class SearchBackend:
    """Base search backend."""
    
    def search(self, query, models=None):
        """Search for the query in the given models."""
        raise NotImplementedError("Subclasses must implement this method")


class DatabaseSearchBackend(SearchBackend):
    """Database search backend using Django ORM."""
    
    def search(self, query, models=None):
        """Search for the query in the given models."""
        if not query:
            return {}
            
        results = {}
        
        # Get models to search
        if models is None:
            models = ['article', 'author', 'category', 'tag']
            
        # Search each model
        for model_name in models:
            model = model_registry.get_model(model_name)
            if not model:
                logger.warning(f'Model {model_name} not found in registry')
                continue
                
            # Get search fields for the model
            search_fields = self._get_search_fields(model_name)
            
            # Build query
            q_objects = Q()
            for field in search_fields:
                q_objects |= Q(**{f'{field}__icontains': query})
                
            # Filter queryset
            queryset = model.objects.filter(q_objects)
            
            # Add status filters for relevant models
            if model_name == 'article':
                queryset = queryset.filter(status='published')
            elif model_name == 'author':
                queryset = queryset.filter(is_active=True)
            elif model_name == 'category':
                queryset = queryset.filter(is_active=True)
                
            # Store results
            results[model_name] = queryset
            
        return results
    
    def _get_search_fields(self, model_name):
        """Get search fields for a model."""
        if model_name == 'article':
            return settings.SEARCH.get('fields', ['title', 'content', 'summary'])
        elif model_name == 'author':
            return ['display_name', 'bio']
        elif model_name == 'category':
            return ['name', 'description']
        elif model_name == 'tag':
            return ['name', 'description']
        elif model_name == 'comment':
            return ['content', 'author_name']
        else:
            return ['name', 'title', 'description']


# Factory function
def get_search_backend():
    """Get the configured search backend."""
    from django.utils.module_loading import import_string
    
    backend_path = settings.SEARCH.get('backend', 'flex_blog.search.backends.DatabaseSearchBackend')
    try:
        backend_class = import_string(backend_path)
        return backend_class()
    except ImportError as e:
        logger.error(f'Could not import search backend {backend_path}: {e}')
        # Fall back to database backend
        return DatabaseSearchBackend()
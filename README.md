A sophisticated, flexible Django blog system designed for easy integration and maximum customization.

## Features

- Complete blog functionality with articles, authors, categories, tags, comments
- Highly customizable through Django settings
- Pure REST API using Django Rest Framework
- Supports both UUID and traditional IDs
- Fully internationalized
- Comprehensive admin interface
- Management commands for common tasks
- Thorough test coverage

## Installation

```bash
pip install django-flex-blog
```

## Quick Start

1. Add to your INSTALLED_APPS:

```python
INSTALLED_APPS = [
    # ...
    'flex_blog',
    'rest_framework',
    'django_filters',
    'taggit',
    'mptt',
]
```

2. Configure in your settings:

```python
FLEX_BLOG = {
    "BLOG_MODELS": {
        # Override default models if needed
        # "article": "myapp.CustomArticle",
    },
    "USE_UUID": True,  # Use UUID fields for primary keys
    # ... more settings
}
```

3. Include the URLs:

```python
from django.urls import path, include

urlpatterns = [
    # ...
    path('blog/api/', include('flex_blog.urls')),
]
```

4. Run migrations:

```bash
python manage.py migrate flex_blog
```

## Documentation

For detailed documentation, visit [Read the Docs](https://django-flex-blog.readthedocs.io/).

## License

MIT

# 5. Main package initialization
# flex_blog/__init__.py
__version__ = '0.1.0'

default_app_config = 'flex_blog.apps.FlexBlogConfig'

# 6. App configuration
# flex_blog/apps.py
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
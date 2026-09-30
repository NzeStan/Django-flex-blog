import re
import uuid
from django.utils.text import slugify as django_slugify
from django.utils.translation import gettext_lazy as _
from django.core.files.storage import default_storage
from flex_blog.conf import settings
from django.utils.module_loading import import_string
import logging

logger = logging.getLogger(__name__)


def generate_unique_slug(instance, title, slug_field="slug"):
    """
    Generate a unique slug based on the title.
    """
    slug = django_slugify(title)
    unique_slug = slug
    ModelClass = instance.__class__
    counter = 1
    
    while ModelClass.objects.filter(**{slug_field: unique_slug}).exists():
        unique_slug = f"{slug}-{counter}"
        counter += 1
        
    return unique_slug


def generate_uuid():
    """
    Generate a UUID.
    """
    return str(uuid.uuid4())


def get_storage_backend():
    """
    Get the configured storage backend.
    """
    storage_path = settings.MEDIA.get('storage_backend')
    try:
        storage_class = import_string(storage_path)
        return storage_class()
    except ImportError:
        logger.warning(f"Could not import storage backend {storage_path}, falling back to default.")
        return default_storage


def get_author_model():
    """
    Get the configured author model.
    """
    from flex_blog.registry import model_registry
    return model_registry.get_model('author')


def sanitize_html(html_content):
    """
    Sanitize HTML content to prevent XSS attacks.
    """
    # This is a very basic implementation
    # In a real-world scenario, you'd use a library like bleach
    # or django-bleach for proper HTML sanitization
    html_content = re.sub(r'<script.*?>.*?</script>', '', html_content, flags=re.DOTALL)
    html_content = re.sub(r'javascript:', '', html_content)
    return html_content


def truncate_text(text, max_length=100):
    """
    Truncate text to a maximum length and add ellipsis.
    """
    if len(text) <= max_length:
        return text
    return text[:max_length].rsplit(' ', 1)[0] + '...'


def generate_excerpt(content, max_length=150):
    """
    Generate an excerpt from content.
    """
    # Remove HTML tags if present
    clean_content = re.sub(r'<.*?>', '', content)
    return truncate_text(clean_content, max_length)


def get_user_model_path():
    """
    Get the path to the user model.
    """
    from django.contrib.auth import get_user_model
    user_model = get_user_model()
    return f"{user_model._meta.app_label}.{user_model._meta.model_name}"


def is_feature_enabled(feature_name):
    """
    Check if a feature is enabled in settings.
    """
    return settings.FEATURES.get(feature_name, False)


def get_model_choices(model_registry, filter_func=None):
    """
    Get choices for a model in the registry.
    """
    choices = []
    for key, model in model_registry.get_all_models().items():
        if filter_func is None or filter_func(model):
            choices.append((key, model._meta.verbose_name))
    return choices

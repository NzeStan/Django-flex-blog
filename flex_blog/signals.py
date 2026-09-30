from django.db.models.signals import pre_save, post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


@receiver(pre_save)
def set_slug_on_save(sender, instance, **kwargs):
    """
    Set a slug before saving if the model has a slug field and it's not set.
    """
    from flex_blog.registry import model_registry
    
    # Skip if this isn't one of our registered models
    if sender not in model_registry.get_all_models().values():
        return
        
    # Check if it has a slug field
    if hasattr(instance, 'slug') and not instance.slug:
        from flex_blog.utils import generate_unique_slug
        # Generate from title or name
        if hasattr(instance, 'title'):
            instance.slug = generate_unique_slug(instance, instance.title)
        elif hasattr(instance, 'name'):
            instance.slug = generate_unique_slug(instance, instance.name)


@receiver(pre_save)
def set_published_date(sender, instance, **kwargs):
    """
    Set published_at when an article is published.
    """
    from flex_blog.registry import model_registry
    
    # Skip if this isn't our Article model
    if sender != model_registry.get_model('article'):
        return
        
    # If this is a new publish action
    if hasattr(instance, 'status') and instance.status == 'published':
        # Get the original instance if it exists
        if instance.pk:
            try:
                original = sender.objects.get(pk=instance.pk)
                if original.status != 'published' and not instance.published_at:
                    instance.published_at = timezone.now()
            except sender.DoesNotExist:
                pass
        # If it's a new instance
        elif not instance.published_at:
            instance.published_at = timezone.now()


@receiver(post_save)
def log_model_changes(sender, instance, created, **kwargs):
    """
    Log model changes.
    """
    from flex_blog.registry import model_registry
    
    # Skip if this isn't one of our registered models
    if sender not in model_registry.get_all_models().values():
        return
        
    if created:
        logger.info(f"Created {sender.__name__} with ID {instance.pk}")
    else:
        logger.info(f"Updated {sender.__name__} with ID {instance.pk}")


@receiver(pre_delete)
def log_model_deletion(sender, instance, **kwargs):
    """
    Log model deletion.
    """
    from flex_blog.registry import model_registry
    
    # Skip if this isn't one of our registered models
    if sender not in model_registry.get_all_models().values():
        return
        
    logger.info(f"Deleting {sender.__name__} with ID {instance.pk}")

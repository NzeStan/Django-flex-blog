import uuid

from django.db import IntegrityError, models, transaction
from django.utils.crypto import get_random_string
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from flex_blog.conf import blog_settings


class BaseModel(models.Model):
    """UUID primary key (not enumerable from the API) plus timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True


class ExtraDataMixin(models.Model):
    """Free-form JSON for project specific data without needing a migration."""

    extra_data = models.JSONField(_("extra data"), default=dict, blank=True)

    class Meta:
        abstract = True


def unique_slugify(instance, value, *, field_name="slug", max_length=None):
    """Return a slug derived from ``value`` that is unused by other rows."""
    field = instance._meta.get_field(field_name)
    max_length = max_length or field.max_length
    allow_unicode = blog_settings.ARTICLES["slug_allow_unicode"]
    base = slugify(value or "", allow_unicode=allow_unicode)[: max_length - 9].strip("-")
    if not base:
        base = get_random_string(8).lower()
    qs = type(instance)._default_manager.all()
    if instance.pk:
        qs = qs.exclude(pk=instance.pk)
    candidate = base
    for index in range(2, 52):
        if not qs.filter(**{field_name: candidate}).exists():
            return candidate
        candidate = f"{base}-{index}"
    return f"{base}-{get_random_string(6).lower()}"


class SlugMixin(models.Model):
    """
    Fills ``slug`` from ``slug_source`` when blank.

    Two concurrent saves can pick the same free slug; the loser of that race
    gets an IntegrityError, so we retry with a fresh slug instead of failing.
    """

    slug_source = "name"
    slug = models.SlugField(_("slug"), max_length=255, unique=True, allow_unicode=True, blank=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.slug:
            return super().save(*args, **kwargs)
        for attempt in range(5):
            self.slug = unique_slugify(self, getattr(self, self.slug_source))
            if attempt:
                self.slug = f"{self.slug[:240]}-{get_random_string(6).lower()}"
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                taken = type(self)._default_manager.filter(slug=self.slug).exclude(pk=self.pk).exists()
                if not taken or attempt == 4:
                    raise

import os
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from flex_blog.conf import blog_settings
from flex_blog.models.base import BaseModel, ExtraDataMixin
from flex_blog.validators import validate_upload


def media_storage():
    """Storage for every file the blog stores (callable, so it never ends up in migrations)."""
    from django.core.files.storage import default_storage, storages

    alias = blog_settings.MEDIA["storage"]
    return storages[alias] if alias else default_storage


def upload_to(instance, filename):
    """
    Random file names: user supplied names never touch the storage path, which
    rules out path traversal and collisions, and avoids leaking original names.
    """
    ext = os.path.splitext(filename)[1].lower()[:10]
    folder = timezone.now().strftime(blog_settings.MEDIA["upload_to"])
    return f"{folder}{uuid.uuid4().hex}{ext}"


class Media(BaseModel, ExtraDataMixin):
    class Kind(models.TextChoices):
        IMAGE = "image", _("Image")
        VIDEO = "video", _("Video")
        AUDIO = "audio", _("Audio")
        DOCUMENT = "document", _("Document")
        OTHER = "other", _("Other")

    file = models.FileField(_("file"), upload_to=upload_to, storage=media_storage, max_length=255, validators=[validate_upload])
    title = models.CharField(_("title"), max_length=255, blank=True)
    alt_text = models.CharField(_("alt text"), max_length=255, blank=True)
    caption = models.TextField(_("caption"), blank=True)
    kind = models.CharField(_("kind"), max_length=20, choices=Kind.choices, default=Kind.OTHER, editable=False, db_index=True)
    mime_type = models.CharField(_("MIME type"), max_length=100, blank=True, editable=False)
    size = models.PositiveBigIntegerField(_("size"), default=0, editable=False)
    width = models.PositiveIntegerField(_("width"), null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(_("height"), null=True, blank=True, editable=False)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="blog_media", verbose_name=_("uploaded by"),
    )

    class Meta:
        verbose_name = _("media file")
        verbose_name_plural = _("media library")
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or os.path.basename(self.file.name)

    def save(self, *args, **kwargs):
        if self.file and not self.size:
            self._inspect_file()
        if not self.title and self.file:
            self.title = os.path.splitext(os.path.basename(getattr(self.file, "name", "")))[0][:255]
        super().save(*args, **kwargs)

    def _inspect_file(self):
        import mimetypes

        self.size = getattr(self.file, "size", 0) or 0
        name = getattr(self.file, "name", "") or ""
        self.mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        major = self.mime_type.split("/")[0]
        if major in ("image", "video", "audio"):
            self.kind = major
        elif self.mime_type in ("application/pdf", "text/plain") or name.lower().endswith((".doc", ".docx")):
            self.kind = self.Kind.DOCUMENT
        if self.kind == self.Kind.IMAGE:
            from flex_blog.validators import image_dimensions

            self.width, self.height = image_dimensions(self.file)

    @property
    def url(self):
        return self.file.url if self.file else ""

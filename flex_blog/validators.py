import os

from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext_lazy as _

from flex_blog.conf import blog_settings

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "avif"}
# Pillow format name -> extensions that may legitimately carry it.
IMAGE_FORMATS = {
    "JPEG": {"jpg", "jpeg"},
    "MPO": {"jpg", "jpeg"},
    "PNG": {"png"},
    "GIF": {"gif"},
    "WEBP": {"webp"},
    "AVIF": {"avif"},
}


def _extension(file):
    return os.path.splitext(getattr(file, "name", "") or "")[1].lower().lstrip(".")


def validate_file_size(file):
    limit = blog_settings.MEDIA["max_upload_size"]
    if limit and getattr(file, "size", 0) and file.size > limit:
        raise ValidationError(
            _("File is too large (%(size)s). The limit is %(limit)s."),
            code="file_too_large",
            params={"size": filesizeformat(file.size), "limit": filesizeformat(limit)},
        )


def validate_image_content(file):
    """
    Open the file with Pillow and check it really is the image its extension
    claims. Stops polyglot files, HTML/SVG renamed to .png, and decompression
    bombs.
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is a hard dependency
        return
    ext = _extension(file)
    position = file.tell() if hasattr(file, "tell") else None
    try:
        file.seek(0)
        with Image.open(file) as image:
            fmt = image.format
            width, height = image.size
            image.verify()
    except Image.DecompressionBombError:
        raise ValidationError(_("Image dimensions are too large."), code="image_too_large")
    except Exception:
        raise ValidationError(_("Upload a valid image. The file is not an image or is corrupted."), code="invalid_image")
    finally:
        if position is not None:
            file.seek(position)
    max_pixels = blog_settings.MEDIA["max_image_pixels"]
    if max_pixels and width * height > max_pixels:
        raise ValidationError(_("Image dimensions are too large."), code="image_too_large")
    if ext not in IMAGE_FORMATS.get(fmt, set()):
        raise ValidationError(_("The file extension does not match the image content."), code="extension_mismatch")


def validate_image_upload(file):
    """For image-only fields (covers, avatars)."""
    validate_file_size(file)
    if _extension(file) not in IMAGE_EXTENSIONS:
        raise ValidationError(
            _("Unsupported image type. Allowed: %(allowed)s."),
            code="invalid_extension",
            params={"allowed": ", ".join(sorted(IMAGE_EXTENSIONS))},
        )
    if not getattr(file, "_committed", False):
        validate_image_content(file)


def validate_upload(file):
    """For the media library: size, extension allow-list and image sniffing."""
    validate_file_size(file)
    allowed = {e.lower().lstrip(".") for e in blog_settings.MEDIA["allowed_extensions"]}
    ext = _extension(file)
    if ext not in allowed:
        raise ValidationError(
            _("Unsupported file type. Allowed: %(allowed)s."),
            code="invalid_extension",
            params={"allowed": ", ".join(sorted(allowed))},
        )
    if ext in IMAGE_EXTENSIONS and not getattr(file, "_committed", False):
        validate_image_content(file)


def image_dimensions(file):
    try:
        from PIL import Image

        position = file.tell()
        file.seek(0)
        with Image.open(file) as image:
            size = image.size
        file.seek(position)
        return size
    except Exception:
        return None, None

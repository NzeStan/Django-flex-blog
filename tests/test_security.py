import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from flex_blog.models import Media

from .conftest import API, client_for

pytestmark = pytest.mark.django_db


def png_file(name="pic.png", size=(4, 3), fmt="PNG"):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, "red").save(buffer, format=fmt)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def test_media_upload_valid_image(author_user):
    response = client_for(author_user).post(f"{API}/media/", {"file": png_file(), "alt_text": "red"}, format="multipart")
    assert response.status_code == 201, response.data
    assert response.data["kind"] == "image"
    assert (response.data["width"], response.data["height"]) == (4, 3)
    media = Media.objects.get()
    assert media.uploaded_by == author_user
    assert "pic" not in media.file.name  # random storage names


@pytest.mark.parametrize(
    "upload",
    [
        SimpleUploadedFile("evil.png", b"<html><script>alert(1)</script></html>", content_type="image/png"),
        SimpleUploadedFile("evil.svg", b"<svg onload=alert(1)>", content_type="image/svg+xml"),
        SimpleUploadedFile("shell.php", b"<?php ?>", content_type="text/plain"),
    ],
)
def test_media_upload_rejects_dangerous_files(author_user, upload):
    response = client_for(author_user).post(f"{API}/media/", {"file": upload}, format="multipart")
    assert response.status_code == 400
    assert not Media.objects.exists()


def test_media_upload_rejects_mismatched_extension(author_user):
    upload = png_file(name="photo.jpg")
    assert client_for(author_user).post(f"{API}/media/", {"file": upload}, format="multipart").status_code == 400


def test_media_upload_size_limit(settings, author_user):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "MEDIA": {"max_upload_size": 10}}
    assert client_for(author_user).post(f"{API}/media/", {"file": png_file()}, format="multipart").status_code == 400


def test_media_pixel_limit(settings, author_user):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "MEDIA": {"max_image_pixels": 10}}
    assert client_for(author_user).post(f"{API}/media/", {"file": png_file()}, format="multipart").status_code == 400


def test_media_requires_author_and_is_private(author_user, reader, editor):
    assert client_for(reader).get(f"{API}/media/").status_code == 403
    client_for(author_user).post(f"{API}/media/", {"file": png_file()}, format="multipart")
    media = Media.objects.get()
    other = client_for(editor)  # editor fixture lacks change_media
    assert other.get(f"{API}/media/").status_code == 403 or other.get(f"{API}/media/").data["count"] == 0
    owner = client_for(author_user)
    assert owner.patch(f"{API}/media/{media.pk}/", {"title": "Renamed"}).data["title"] == "Renamed"
    assert owner.delete(f"{API}/media/{media.pk}/").status_code == 204


def test_comment_throttled(settings, reader, article):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "THROTTLE_RATES": {"comments": "2/min"}}
    client = client_for(reader)
    codes = [client.post(f"{API}/articles/{article.slug}/comments/", {"content": f"Comment {i}"}).status_code for i in range(3)]
    assert codes == [201, 201, 429]


def test_write_throttle_applies_to_articles(settings, author_user):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "THROTTLE_RATES": {"write": "1/min"}}
    client = client_for(author_user)
    assert client.post(f"{API}/articles/", {"title": "One"}).status_code == 201
    assert client.post(f"{API}/articles/", {"title": "Two"}).status_code == 429


def test_comment_xss_is_neutralised(reader, article):
    response = client_for(reader).post(
        f"{API}/articles/{article.slug}/comments/",
        {"content": "<script>alert(1)</script> [x](javascript:alert(1)) <b onmouseover=x>hi</b>"},
    )
    html = response.data["content_html"]
    assert "<script" not in html and 'href="javascript' not in html and "<b " not in html
    assert "&lt;script&gt;" in html  # shown as text, never executed


def test_private_fields_never_exposed(anon, reader, article):
    client_for(reader).post(f"{API}/articles/{article.slug}/comments/", {"content": "Hello there"})
    from flex_blog.models import Comment

    Comment.objects.update(status="approved")
    data = anon.get(f"{API}/articles/{article.slug}/comments/").data["results"][0]
    assert "email" not in data["author"] and "ip_address" not in data["author"]
    assert data["content"] is None


def test_webhook_url_validation(settings):
    from django.core.exceptions import ValidationError

    from flex_blog.webhooks import validate_webhook_url

    for url in ("http://example.com/hook", "https://127.0.0.1/hook", "https://localhost/hook", "ftp://x"):
        with pytest.raises(ValidationError):
            validate_webhook_url(url)
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "WEBHOOKS": {"allow_http": True, "allow_private_hosts": True}}
    validate_webhook_url("http://127.0.0.1/hook")

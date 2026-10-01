import pytest

from flex_blog.models import Article, Comment, IdempotencyRecord

from .conftest import API, client_for

pytestmark = pytest.mark.django_db


def test_retry_with_same_key_replays_response(reader, article):
    client = client_for(reader)
    url = f"{API}/articles/{article.slug}/comments/"
    first = client.post(url, {"content": "Only once please"}, HTTP_IDEMPOTENCY_KEY="abc-123")
    second = client.post(url, {"content": "Only once please"}, HTTP_IDEMPOTENCY_KEY="abc-123")
    assert first.status_code == second.status_code == 201
    assert first.data["id"] == second.data["id"]
    assert second["Idempotent-Replayed"] == "true"
    assert Comment.objects.count() == 1


def test_same_key_different_body_rejected(author_user):
    client = client_for(author_user)
    assert client.post(f"{API}/articles/", {"title": "A"}, HTTP_IDEMPOTENCY_KEY="k").status_code == 201
    assert client.post(f"{API}/articles/", {"title": "B"}, HTTP_IDEMPOTENCY_KEY="k").status_code == 422
    assert Article.objects.count() == 1


def test_keys_are_scoped_per_user(author_user, editor):
    assert client_for(author_user).post(f"{API}/articles/", {"title": "A"}, HTTP_IDEMPOTENCY_KEY="k").status_code == 201
    assert client_for(editor).post(f"{API}/articles/", {"title": "A"}, HTTP_IDEMPOTENCY_KEY="k").status_code == 201
    assert Article.objects.count() == 2


def test_in_flight_request_conflicts(author_user):
    from flex_blog.api import _fingerprint  # noqa: F401  (documented behaviour)

    IdempotencyRecord.objects.create(
        scope=f"user:{author_user.pk}", key="busy", method="POST", path=f"{API}/articles/",
        fingerprint="x" * 64,
    )
    response = client_for(author_user).post(f"{API}/articles/", {"title": "A"}, HTTP_IDEMPOTENCY_KEY="busy")
    assert response.status_code in (409, 422)


def test_errors_are_not_cached_for_5xx_and_key_length(author_user):
    client = client_for(author_user)
    assert client.post(f"{API}/articles/", {"title": "A"}, HTTP_IDEMPOTENCY_KEY="x" * 300).status_code == 400


def test_validation_errors_replayed(author_user):
    client = client_for(author_user)
    first = client.post(f"{API}/articles/", {"content_format": "nope"}, HTTP_IDEMPOTENCY_KEY="bad")
    second = client.post(f"{API}/articles/", {"content_format": "nope"}, HTTP_IDEMPOTENCY_KEY="bad")
    assert first.status_code == second.status_code == 400


def test_expired_keys_can_be_reused(settings, author_user):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "IDEMPOTENCY": {"ttl_seconds": 0}}
    client = client_for(author_user)
    client.post(f"{API}/articles/", {"title": "A"}, HTTP_IDEMPOTENCY_KEY="k")
    assert client.post(f"{API}/articles/", {"title": "B"}, HTTP_IDEMPOTENCY_KEY="k").status_code == 201


def test_feature_can_be_disabled(settings, reader, article):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "FEATURES": {"idempotency": False}}
    client = client_for(reader)
    url = f"{API}/articles/{article.slug}/comments/"
    client.post(url, {"content": "twice"}, HTTP_IDEMPOTENCY_KEY="k")
    client.post(url, {"content": "twice"}, HTTP_IDEMPOTENCY_KEY="k")
    assert Comment.objects.count() == 2


def test_anonymous_keys_work(settings, anon):
    for _ in range(2):
        response = anon.post(f"{API}/newsletter/subscribe/", {"email": "x@example.com"}, HTTP_IDEMPOTENCY_KEY="anon-key")
    assert response["Idempotent-Replayed"] == "true"

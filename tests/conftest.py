from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from flex_blog.models import Article, Author, Category, Tag

API = "/api/blog"


@pytest.fixture(autouse=True)
def _isolation(settings, tmp_path, monkeypatch):
    """Clean cache per test, temp media dir, and run on_commit callbacks immediately."""
    cache.clear()
    settings.MEDIA_ROOT = str(tmp_path)
    from django.db import transaction

    monkeypatch.setattr(transaction, "on_commit", lambda func, using=None, robust=False: func())
    yield
    cache.clear()


def make_user(username, *perms, **extra):
    user = get_user_model().objects.create_user(username=username, email=f"{username}@example.com", password="pw", **extra)
    if perms:
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label="flex_blog", codename__in=perms))
        user = get_user_model().objects.get(pk=user.pk)  # reset the permission cache
    return user


@pytest.fixture
def reader(db):
    return make_user("reader")


@pytest.fixture
def author_user(db):
    return make_user("writer", "add_article", "add_media", "publish_article")


@pytest.fixture
def junior_author(db):
    """Can write but not publish."""
    return make_user("junior", "add_article")


@pytest.fixture
def editor(db):
    return make_user(
        "editor", "add_article", "change_article", "delete_article", "publish_article",
        "add_category", "change_category", "delete_category", "add_tag", "change_tag", "delete_tag",
        "add_series", "change_series",
    )


@pytest.fixture
def moderator(db):
    return make_user("moderator", "moderate_comment")


@pytest.fixture
def admin_user(db):
    return get_user_model().objects.create_superuser("admin", "admin@example.com", "pw")


def client_for(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user)
    return client


@pytest.fixture
def anon():
    return client_for()


@pytest.fixture
def author(author_user):
    return Author.for_user(author_user)


@pytest.fixture
def category(db):
    return Category.objects.create(name="Technology")


@pytest.fixture
def tag(db):
    return Tag.objects.create(name="Django")


def make_article(author, title="Hello world", status=Article.Status.PUBLISHED, **kwargs):
    kwargs.setdefault("content", "Some **bold** text with enough words to read.")
    if status == Article.Status.PUBLISHED:
        kwargs.setdefault("published_at", timezone.now() - timedelta(minutes=5))
    return Article.objects.create(title=title, author=author, status=status, **kwargs)


@pytest.fixture
def article(author, category, tag):
    article = make_article(author)
    article.categories.add(category)
    article.tags.add(tag)
    return article


@pytest.fixture
def draft(author):
    return make_article(author, title="Secret draft", status=Article.Status.DRAFT)

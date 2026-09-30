import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from flex_blog.registry import model_registry

User = get_user_model()

@pytest.fixture
def api_client():
    """Return an API client."""
    return APIClient()

@pytest.fixture
def user():
    """Create a test user."""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='password'
    )

@pytest.fixture
def staff_user():
    """Create a test staff user."""
    return User.objects.create_user(
        username='staffuser',
        email='staff@example.com',
        password='password',
        is_staff=True
    )

@pytest.fixture
def authenticated_client(api_client, user):
    """Return an authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client

@pytest.fixture
def staff_client(api_client, staff_user):
    """Return an authenticated staff API client."""
    api_client.force_authenticate(user=staff_user)
    return api_client

@pytest.fixture
def author(user):
    """Create a test author."""
    Author = model_registry.get_model('author')
    return Author.objects.create(
        user=user,
        display_name='Test Author',
        bio='Test bio'
    )

@pytest.fixture
def category():
    """Create a test category."""
    Category = model_registry.get_model('category')
    return Category.objects.create(
        name='Test Category',
        slug='test-category',
        description='Test description'
    )

@pytest.fixture
def tag():
    """Create a test tag."""
    Tag = model_registry.get_model('tag')
    return Tag.objects.create(
        name='Test Tag',
        slug='test-tag',
        description='Test description'
    )

@pytest.fixture
def article(author, category, tag):
    """Create a test article."""
    Article = model_registry.get_model('article')
    article = Article.objects.create(
        title='Test Article',
        slug='test-article',
        content='Test content',
        summary='Test summary',
        author=author,
        status='published'
    )
    article.categories.add(category)
    article.tags.add(tag)
    return article

@pytest.fixture
def comment(article, user):
    """Create a test comment."""
    Comment = model_registry.get_model('comment')
    return Comment.objects.create(
        article=article,
        author_name='Test Commenter',
        author_email='commenter@example.com',
        content='Test comment',
        user=user,
        is_approved=True
    )


import pytest
from flex_blog.registry import model_registry
from django.utils import timezone
from datetime import timedelta
import uuid


@pytest.mark.django_db
class TestArticleModel:
    """Test the Article model."""

    def test_create_article(self, author):
        """Test creating an article."""
        Article = model_registry.get_model('article')
        article = Article.objects.create(
            title='Test Title',
            slug='test-title',
            content='Test content',
            author=author
        )

        # Assertions to confirm the article was created
        assert article.title == 'Test Title'
        assert article.slug == 'test-title'
        assert article.content == 'Test content'
        assert article.author == author

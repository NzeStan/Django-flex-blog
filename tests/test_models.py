from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from flex_blog.models import Article, ArticleRevision, Author, Category, SlugRedirect, Tag
from flex_blog.rendering import render_comment, render_content
from flex_blog.services import articles as article_service

from .conftest import make_article, make_user

pytestmark = pytest.mark.django_db


def test_slug_generated_and_unique(author):
    first = make_article(author, title="Same title")
    second = make_article(author, title="Same title")
    assert first.slug == "same-title"
    assert second.slug == "same-title-2"


def test_explicit_slug_kept(author):
    assert make_article(author, slug="custom").slug == "custom"


def test_empty_title_slug_falls_back_to_random(author):
    article = make_article(author, title="!!!")
    assert article.slug


def test_uuid_primary_keys(article):
    assert len(str(article.pk)) == 36


def test_markdown_rendered_and_sanitised(author):
    article = make_article(
        author,
        content="# Title\n\n## Part one\n\nHello <script>alert(1)</script> [x](javascript:alert(1)) <img src=x onerror=alert(1)>\n\n## Part one",
    )
    html = article.content_html
    assert "<script" not in html and "alert(1)</" not in html
    assert 'href="javascript' not in html
    assert "onerror" not in html
    assert article.table_of_contents == [
        {"id": "part-one", "text": "Part one", "level": 2},
        {"id": "part-one-2", "text": "Part one", "level": 2},
    ]
    assert 'id="part-one"' in html


def test_html_content_sanitised(author):
    article = make_article(author, content_format="html", content='<p onclick="x()">Hi<iframe src="https://evil"></iframe><a href="https://ok.com">ok</a></p>')
    assert "onclick" not in article.content_html
    assert "iframe" not in article.content_html
    assert 'rel="noopener noreferrer nofollow"' in article.content_html


def test_plain_content_escaped(author):
    article = make_article(author, content_format="plain", content="<b>not bold</b>\n\nsecond")
    assert "&lt;b&gt;" in article.content_html
    assert article.content_html.count("<p>") == 2


def test_reading_time_word_count_and_excerpt(author):
    article = make_article(author, content=" ".join(["word"] * 450))
    assert article.word_count == 450
    assert article.reading_time == 3
    assert article.excerpt.endswith("…")
    article.summary = "Custom summary"
    article.save()
    assert article.excerpt == "Custom summary"


def test_comment_rendering_restricted():
    html = render_comment("# heading\n\n![img](https://x/y.png) **ok**")
    assert "<h1" not in html and "<img" not in html and "<strong>ok</strong>" in html


def test_render_content_empty():
    rendered = render_content("", "markdown")
    assert rendered.word_count == 0 and rendered.reading_time == 0


def test_publish_sets_published_at_and_announces_once(author, django_assert_num_queries):
    from flex_blog.signals import article_published

    events = []
    article_published.connect(lambda **kw: events.append(kw["article"].pk), weak=False, dispatch_uid="t1")
    try:
        article = make_article(author, status=Article.Status.DRAFT)
        assert article.published_at is None
        article.status = Article.Status.PUBLISHED
        article.save()
        article.refresh_from_db()
        assert article.published_at is not None
        assert article.announced_at is not None
        # Re-saving, unpublishing and re-publishing never re-announces.
        article.save()
        article.status = Article.Status.DRAFT
        article.save()
        article.status = Article.Status.PUBLISHED
        article.save()
        assert article_service.announce(article.pk) is False
        assert events == [article.pk]
    finally:
        article_published.disconnect(dispatch_uid="t1")


def test_scheduled_article_hidden_until_due(author):
    future = make_article(author, title="Later", published_at=timezone.now() + timedelta(hours=1))
    assert future.is_scheduled and not future.is_live
    assert not Article.objects.published().filter(pk=future.pk).exists()
    assert future.announced_at is None
    Article.objects.filter(pk=future.pk).update(published_at=timezone.now() - timedelta(seconds=1))
    assert article_service.announce_due() == 1
    assert article_service.announce_due() == 0


def test_revision_captured_on_content_change(article, author_user):
    article.title = "Changed"
    article._editor = author_user
    article.save()
    revision = ArticleRevision.objects.get(article=article)
    assert revision.title == "Hello world"
    assert revision.editor == author_user
    article.is_featured = True
    article.save()
    assert ArticleRevision.objects.filter(article=article).count() == 1


def test_version_increments(article):
    version = article.version
    article.save()
    assert article.version == version + 1


def test_slug_redirect_recorded(article):
    old = article.slug
    article.slug = "new-slug"
    article.save()
    assert SlugRedirect.objects.get(old_slug=old).article == article
    article.slug = old
    article.save()
    assert not SlugRedirect.objects.filter(old_slug=old).exists()


def test_category_cycle_rejected(db):
    parent = Category.objects.create(name="Parent")
    child = Category.objects.create(name="Child", parent=parent)
    parent.parent = child
    with pytest.raises(ValidationError):
        parent.full_clean()
    assert set(parent.get_descendant_ids()) == {parent.pk, child.pk}


def test_author_for_user_is_idempotent(db):
    user = make_user("someone", first_name="Ada", last_name="Obi")
    first = Author.for_user(user)
    assert Author.for_user(user) == first
    assert first.display_name == "Ada Obi"


def test_set_tags_creates_and_reuses(article):
    Tag.objects.create(name="Python")
    article_service.set_tags(article, ["python", "New Tag", " new   tag ", ""])
    assert sorted(article.tags.values_list("slug", flat=True)) == ["new-tag", "python"]


def test_readable_by(article, draft, reader, editor):
    assert set(Article.objects.readable_by(reader)) == {article}
    assert set(Article.objects.readable_by(editor)) == {article, draft}
    assert set(Article.objects.readable_by(draft.author.user)) == {article, draft}

from datetime import timedelta

import pytest
from django.utils import timezone

from flex_blog.models import Article, ArticleRevision, Author, Category, Tag

from .conftest import API, client_for, make_article, make_user

pytestmark = pytest.mark.django_db


def slugs(response):
    return [row["slug"] for row in response.data["results"]]


# --- reading -------------------------------------------------------------------


def test_list_shows_only_live_listed_articles(anon, article, draft, author):
    make_article(author, title="Unlisted", visibility=Article.Visibility.UNLISTED)
    make_article(author, title="Future", published_at=timezone.now() + timedelta(days=1))
    make_article(author, title="Archived", status=Article.Status.ARCHIVED)
    response = anon.get(f"{API}/articles/")
    assert response.status_code == 200
    assert slugs(response) == [article.slug]
    row = response.data["results"][0]
    assert row["author"]["display_name"] == author.display_name
    assert row["url"] == f"/blog/{article.slug}/"
    assert "content" not in row  # lists stay light


def test_detail_hides_drafts_from_public(anon, draft, reader):
    assert anon.get(f"{API}/articles/{draft.slug}/").status_code == 404
    assert client_for(reader).get(f"{API}/articles/{draft.slug}/").status_code == 404
    owner = client_for(draft.author.user)
    response = owner.get(f"{API}/articles/{draft.slug}/")
    assert response.status_code == 200
    assert response.data["content"] == draft.content
    assert response.data["viewer"]["can_edit"] is True


def test_detail_raw_content_only_for_editors(anon, article):
    response = anon.get(f"{API}/articles/{article.slug}/")
    assert response.data["content"] is None
    assert "<strong>bold</strong>" in response.data["content_html"]


def test_unlisted_reachable_by_link(anon, author):
    hidden = make_article(author, title="Hidden", visibility=Article.Visibility.UNLISTED)
    assert anon.get(f"{API}/articles/{hidden.slug}/").status_code == 200


def test_members_only_content_locked(anon, reader, author):
    gated = make_article(author, title="Premium", visibility=Article.Visibility.MEMBERS)
    locked = anon.get(f"{API}/articles/{gated.slug}/").data
    assert locked["is_locked"] is True and locked["content_html"] == ""
    unlocked = client_for(reader).get(f"{API}/articles/{gated.slug}/").data
    assert unlocked["is_locked"] is False and unlocked["content_html"]


def test_content_access_check_hook(settings, reader, author):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "CONTENT_ACCESS_CHECK": "tests.hooks.deny_all"}
    gated = make_article(author, title="Paid", visibility=Article.Visibility.MEMBERS)
    assert client_for(reader).get(f"{API}/articles/{gated.slug}/").data["is_locked"] is True


def test_views_counted_once_per_reader(anon, article, reader):
    for _ in range(3):
        anon.get(f"{API}/articles/{article.slug}/")
    client_for(reader).get(f"{API}/articles/{article.slug}/")
    article.refresh_from_db()
    assert article.views_count == 2


def test_view_counting_disabled(settings, anon, article):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "FEATURES": {"view_counting": False}}
    anon.get(f"{API}/articles/{article.slug}/")
    article.refresh_from_db()
    assert article.views_count == 0


def test_filters(anon, author, article, category, tag):
    child = Category.objects.create(name="Python", parent=category)
    other = make_article(author, title="Other", language="yo")
    other.categories.add(child)
    assert set(slugs(anon.get(f"{API}/articles/?category={category.slug}"))) == {article.slug, other.slug}
    assert slugs(anon.get(f"{API}/articles/?category={child.slug}")) == [other.slug]
    assert slugs(anon.get(f"{API}/articles/?tag={tag.slug},nope")) == [article.slug]
    assert slugs(anon.get(f"{API}/articles/?language=yo")) == [other.slug]
    assert slugs(anon.get(f"{API}/articles/?author={author.slug}&ordering=title")) == [article.slug, other.slug]
    assert slugs(anon.get(f"{API}/articles/?category=missing")) == []


def test_pinned_first_and_pagination(anon, author):
    for i in range(5):
        make_article(author, title=f"A{i}")
    pinned = make_article(author, title="Pinned", is_pinned=True, published_at=timezone.now() - timedelta(days=30))
    response = anon.get(f"{API}/articles/?page_size=2")
    assert response.data["count"] == 6
    assert len(response.data["results"]) == 2
    assert response.data["results"][0]["slug"] == pinned.slug


def test_search(anon, author):
    make_article(author, title="Jollof rice recipe", content="Tomatoes and pepper")
    make_article(author, title="Suya", content="A spicy jollof side")
    make_article(author, title="Unrelated")
    response = anon.get(f"{API}/articles/?q=jollof")
    assert slugs(response)[0] == "jollof-rice-recipe"
    assert len(slugs(response)) == 2
    assert slugs(anon.get(f"{API}/articles/?q=jollof pepper")) == ["jollof-rice-recipe"]


def test_global_search(anon, article, category):
    response = anon.get(f"{API}/search/?q=hello")
    assert response.status_code == 200
    assert response.data["articles"][0]["slug"] == article.slug
    assert anon.get(f"{API}/search/?q=t").status_code == 400
    assert anon.get(f"{API}/search/?q=techno").data["categories"][0]["slug"] == category.slug


def test_related_popular_archive(anon, author, article, tag):
    sibling = make_article(author, title="Sibling")
    sibling.tags.add(tag)
    make_article(author, title="Lonely")
    assert [a["slug"] for a in anon.get(f"{API}/articles/{article.slug}/related/").data] == [sibling.slug]
    Article.objects.filter(pk=sibling.pk).update(views_count=50)
    assert slugs(anon.get(f"{API}/articles/popular/?days=7"))[0] == sibling.slug
    assert anon.get(f"{API}/articles/popular/?days=x").status_code == 400
    archive = anon.get(f"{API}/articles/archive/").data
    assert archive[0]["count"] == 3


def test_slug_redirect(anon, article):
    old = article.slug
    article.slug = "renamed"
    article.save()
    response = anon.get(f"{API}/articles/{old}/")
    assert response.status_code == 301
    assert response.data["slug"] == "renamed"
    assert response["Location"].endswith("/api/blog/articles/renamed/")


def test_preview_link(anon, draft):
    owner = client_for(draft.author.user)
    token = owner.post(f"{API}/articles/{draft.slug}/preview-link/").data["token"]
    assert anon.get(f"{API}/articles/{draft.slug}/?preview={token}").status_code == 200
    assert anon.get(f"{API}/articles/{draft.slug}/?preview=forged").status_code == 404
    assert anon.post(f"{API}/articles/{draft.slug}/preview-link/").status_code in (401, 403, 404)


def test_series_navigation(anon, author):
    from flex_blog.models import Series

    series = Series.objects.create(title="Course")
    first = make_article(author, title="Part 1", series=series, series_order=1)
    second = make_article(author, title="Part 2", series=series, series_order=2)
    nav = anon.get(f"{API}/articles/{second.slug}/").data["series_navigation"]
    assert nav["previous"]["slug"] == first.slug and nav["next"] is None


# --- writing -------------------------------------------------------------------


def test_create_requires_author_permission(anon, reader):
    payload = {"title": "Nope", "content": "x"}
    assert anon.post(f"{API}/articles/", payload).status_code in (401, 403)
    assert client_for(reader).post(f"{API}/articles/", payload).status_code == 403


def test_author_creates_draft_with_tags(author_user, category):
    client = client_for(author_user)
    response = client.post(f"{API}/articles/", {
        "title": "My first post", "content": "# Hi", "categories": [category.slug], "tags": ["Lagos", "Tech"],
    })
    assert response.status_code == 201, response.data
    assert response.data["status"] == "draft"
    assert {t["name"] for t in response.data["tags"]} == {"Lagos", "Tech"}
    article = Article.objects.get(slug="my-first-post")
    assert article.author == Author.objects.get(user=author_user)


def test_junior_cannot_publish_but_can_submit(junior_author):
    client = client_for(junior_author)
    assert client.post(f"{API}/articles/", {"title": "T", "content": "x", "status": "published"}).status_code == 403
    slug = client.post(f"{API}/articles/", {"title": "T", "content": "x"}).data["slug"]
    assert client.post(f"{API}/articles/{slug}/publish/").status_code == 403
    response = client.post(f"{API}/articles/{slug}/submit/")
    assert response.status_code == 200 and response.data["status"] == "review"


def test_publish_permission_can_be_relaxed(settings, junior_author):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "ARTICLES": {"require_publish_permission": False}}
    client = client_for(junior_author)
    response = client.post(f"{API}/articles/", {"title": "T", "content": "x", "status": "published"})
    assert response.status_code == 201
    assert response.data["published_at"] is not None


def test_publish_action_idempotent_and_schedule(author_user, author):
    article = make_article(author, status=Article.Status.DRAFT)
    client = client_for(author_user)
    first = client.post(f"{API}/articles/{article.slug}/publish/")
    second = client.post(f"{API}/articles/{article.slug}/publish/")
    assert first.status_code == second.status_code == 200
    assert first.data["published_at"] == second.data["published_at"]
    later = (timezone.now() + timedelta(days=2)).isoformat()
    scheduled = client.post(f"{API}/articles/{article.slug}/publish/", {"published_at": later})
    assert scheduled.data["is_scheduled"] is True
    unpublished = client.post(f"{API}/articles/{article.slug}/unpublish/", {"status": "archived"})
    assert unpublished.data["status"] == "archived"
    assert client.post(f"{API}/articles/{article.slug}/unpublish/", {"status": "bogus"}).status_code == 400


def test_non_editor_cannot_set_editor_fields(author_user, author):
    article = make_article(author, status=Article.Status.DRAFT)
    response = client_for(author_user).patch(f"{API}/articles/{article.slug}/", {"is_featured": True})
    assert response.status_code == 403


def test_other_author_cannot_edit(junior_author, article):
    assert client_for(junior_author).patch(f"{API}/articles/{article.slug}/", {"title": "Hacked"}).status_code == 403


def test_editor_can_edit_anything(editor, article):
    response = client_for(editor).patch(f"{API}/articles/{article.slug}/", {"title": "Edited", "is_featured": True})
    assert response.status_code == 200
    assert response.data["title"] == "Edited" and response.data["is_featured"] is True


def test_optimistic_locking(author_user, article):
    client = client_for(author_user)
    version = client.get(f"{API}/articles/{article.slug}/").data["version"]
    assert client.patch(f"{API}/articles/{article.slug}/", {"title": "One", "version": version}).status_code == 200
    stale = client.patch(f"{API}/articles/{article.slug}/", {"title": "Two", "version": version})
    assert stale.status_code == 409
    article.refresh_from_db()
    assert article.title == "One"


def test_validation_limits(settings, author_user):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "ARTICLES": {"max_tags": 2, "content_formats": ["markdown"]}}
    client = client_for(author_user)
    assert client.post(f"{API}/articles/", {"title": "T", "tags": ["a", "b", "c"]}).status_code == 400
    assert client.post(f"{API}/articles/", {"title": "T", "content_format": "html"}).status_code == 400
    assert client.post(f"{API}/articles/", {"title": "T", "language": "xx"}).status_code == 400
    assert client.post(f"{API}/articles/", {"title": "T", "extra_data": []}).status_code == 400


def test_scope_mine_and_all(author_user, editor, reader, article, draft):
    mine = client_for(author_user).get(f"{API}/articles/?scope=mine")
    assert set(slugs(mine)) == {article.slug, draft.slug}
    assert set(slugs(client_for(editor).get(f"{API}/articles/?scope=all"))) == {article.slug, draft.slug}
    assert slugs(client_for(reader).get(f"{API}/articles/?scope=all")) == [article.slug]
    assert slugs(client_for(editor).get(f"{API}/articles/?scope=all&status=draft")) == [draft.slug]


def test_delete(author_user, junior_author, article):
    assert client_for(junior_author).delete(f"{API}/articles/{article.slug}/").status_code == 403
    assert client_for(author_user).delete(f"{API}/articles/{article.slug}/").status_code == 204
    assert not Article.objects.filter(pk=article.pk).exists()


def test_revisions_and_restore(author_user, article):
    client = client_for(author_user)
    client.patch(f"{API}/articles/{article.slug}/", {"title": "Second"})
    revisions = client.get(f"{API}/articles/{article.slug}/revisions/").data["results"]
    assert revisions[0]["title"] == "Hello world"
    restored = client.post(f"{API}/articles/{article.slug}/revisions/{revisions[0]['id']}/restore/")
    assert restored.status_code == 200 and restored.data["title"] == "Hello world"
    assert ArticleRevision.objects.filter(article=article).count() == 2
    assert client_for(make_user("x")).get(f"{API}/articles/{article.slug}/revisions/").status_code == 403
    assert client_for().get(f"{API}/articles/{article.slug}/revisions/").status_code == 403


def test_cover_image_upload(author_user):
    from .test_security import png_file

    response = client_for(author_user).post(
        f"{API}/articles/", {"title": "With cover", "cover_image": png_file(), "cover_image_alt": "alt"}, format="multipart",
    )
    assert response.status_code == 201, response.data
    assert response.data["cover_image"].startswith("http")


# --- caching ------------------------------------------------------------------


def test_anonymous_list_cached_and_invalidated(anon, author, article):
    first = anon.get(f"{API}/articles/")
    second = anon.get(f"{API}/articles/")
    assert first["X-Cache"] == "MISS" and second["X-Cache"] == "HIT"
    make_article(author, title="Fresh")
    third = anon.get(f"{API}/articles/")
    assert third["X-Cache"] == "MISS"
    assert "fresh" in slugs(third)


def test_authenticated_requests_bypass_cache(reader, article):
    client = client_for(reader)
    client.get(f"{API}/articles/")
    assert "X-Cache" not in client.get(f"{API}/articles/")


# --- taxonomy -----------------------------------------------------------------


def test_categories_tree_and_counts(anon, editor, article, category):
    Category.objects.create(name="Child", parent=category)
    Category.objects.create(name="Hidden", is_active=False)
    tree = anon.get(f"{API}/categories/tree/").data
    assert tree[0]["slug"] == category.slug
    assert tree[0]["children"][0]["slug"] == "child"
    assert tree[0]["article_count"] == 1
    assert anon.post(f"{API}/categories/", {"name": "X"}).status_code in (401, 403)
    created = client_for(editor).post(f"{API}/categories/", {"name": "Lifestyle", "parent": category.slug})
    assert created.status_code == 201 and created.data["parent"] == category.slug
    loop = client_for(editor).patch(f"{API}/categories/{category.slug}/", {"parent": "lifestyle"})
    assert loop.status_code == 400
    assert anon.get(f"{API}/categories/?parent=none").data["count"] == 1  # "Hidden" is inactive


def test_draft_counts_do_not_leak(anon, draft, tag):
    draft.tags.add(tag)
    assert anon.get(f"{API}/tags/{tag.slug}/").data["article_count"] == 0


def test_tags_crud(editor, anon):
    client = client_for(editor)
    assert client.post(f"{API}/tags/", {"name": "Afrobeats"}).status_code == 201
    assert anon.get(f"{API}/tags/afrobeats/").status_code == 200
    assert client.delete(f"{API}/tags/afrobeats/").status_code == 204
    assert not Tag.objects.exists()


def test_authors_and_me(anon, author_user, reader, article, author):
    assert anon.get(f"{API}/authors/").data["results"][0]["article_count"] == 1
    client = client_for(author_user)
    response = client.patch(f"{API}/authors/me/", {"bio": "Writer from Enugu", "social_links": {"x": "https://x.com/me"}})
    assert response.status_code == 200 and response.data["bio"] == "Writer from Enugu"
    assert client.patch(f"{API}/authors/me/", {"social_links": {"x": "not a url"}}).status_code == 400
    assert client_for(reader).get(f"{API}/authors/me/").status_code == 404
    assert anon.get(f"{API}/authors/me/").status_code in (401, 403)


def test_series_crud(editor, anon):
    response = client_for(editor).post(f"{API}/series/", {"title": "Django 101"})
    assert response.status_code == 201
    assert anon.get(f"{API}/series/django-101/").status_code == 200


def test_stats_for_editors_only(editor, reader, article):
    assert client_for(reader).get(f"{API}/stats/").status_code == 403
    data = client_for(editor).get(f"{API}/stats/").data
    assert data["articles"]["published"] == 1


def test_non_publisher_cannot_unpublish_via_patch(settings, junior_author):
    from flex_blog.models import Author

    live = make_article(Author.for_user(junior_author), title="Live")
    client = client_for(junior_author)
    assert client.patch(f"{API}/articles/{live.slug}/", {"status": "draft"}).status_code == 403
    assert client.post(f"{API}/articles/{live.slug}/unpublish/").status_code == 403
    assert client.patch(f"{API}/articles/{live.slug}/", {"title": "Typo fix"}).status_code == 200

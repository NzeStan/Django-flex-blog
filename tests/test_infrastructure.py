"""Tasks, feeds, sitemaps, management commands, admin, checks and feature flags."""

import json
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.test import override_settings

from flex_blog import tasks
from flex_blog.conf import blog_settings
from flex_blog.models import Article, Category, Comment, IdempotencyRecord, Subscriber, Tag

from .conftest import API, client_for, make_article

pytestmark = pytest.mark.django_db


# --- tasks --------------------------------------------------------------------


def test_sync_backend_runs_after_commit(monkeypatch):
    from django.db import transaction

    pending = []
    monkeypatch.setattr(transaction, "on_commit", lambda func, using=None, robust=False: pending.append(func))
    calls = []
    tasks.enqueue(lambda *a: calls.append(a), 1, 2)
    assert calls == []  # nothing before commit
    pending[0]()
    assert calls == [(1, 2)]


def test_sync_backend_swallows_and_logs_errors(caplog):
    def boom():
        raise RuntimeError("x")

    tasks.enqueue(boom)
    assert "background job boom failed" in caplog.text


def test_celery_backend_dispatches(settings):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "TASKS": {"backend": "celery", "queue": "blog"}}
    with mock.patch.object(tasks.announce_article.celery_task, "apply_async") as apply_async:
        tasks.enqueue(tasks.announce_article, "abc")
    apply_async.assert_called_once_with(args=("abc",), kwargs={}, queue="blog")


def test_celery_backend_requires_task(settings):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "TASKS": {"backend": "celery"}}
    with pytest.raises(RuntimeError):
        tasks.enqueue(lambda: None)


def test_celery_tasks_registered():
    assert tasks.run_maintenance.celery_task.name == "flex_blog.run_maintenance"


def test_async_view_counting(settings, anon, article):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "VIEW_COUNTING": {"async": True}}
    anon.get(f"{API}/articles/{article.slug}/")
    article.refresh_from_db()
    assert article.views_count == 1


# --- feeds & sitemaps -----------------------------------------------------------


def test_rss_and_atom(anon, article, category, tag, author):
    make_article(author, title="Draft", status=Article.Status.DRAFT)
    rss = anon.get(f"{API}/feeds/rss/")
    assert rss.status_code == 200
    body = rss.content.decode()
    assert "<title>Hello world</title>" in body and "Draft" not in body
    assert "https://blog.example.com/blog/hello-world/" in body
    assert "<feed" in anon.get(f"{API}/feeds/atom/").content.decode()
    for kind, slug in (("category", category.slug), ("tag", tag.slug), ("author", author.slug)):
        response = anon.get(f"{API}/feeds/{kind}/{slug}/")
        assert response.status_code == 200 and "Hello world" in response.content.decode()
    assert anon.get(f"{API}/feeds/tag/nope/").status_code == 404


def test_sitemap(anon, article, category, tag, author):
    make_article(author, title="Hidden", noindex=True)
    body = anon.get(f"{API}/sitemap.xml").content.decode()
    assert "<loc>https://blog.example.com/blog/hello-world/</loc>" in body
    assert "hidden" not in body
    assert f"/blog/category/{category.slug}/" in body and f"/blog/tag/{tag.slug}/" in body
    assert anon.get(f"{API}/sitemap.xml?p=x").status_code == 404


# --- management commands ----------------------------------------------------------


def run(name, *args):
    out = StringIO()
    call_command(name, *args, stdout=out, stderr=StringIO())
    return out.getvalue()


def test_export_import_roundtrip_is_idempotent(tmp_path, article, reader):
    Comment.objects.create(article=article, user=reader, content="Keep me", status="approved")
    parent_slug = article.categories.first().slug
    child = Category.objects.create(name="Child", parent=article.categories.first())
    path = tmp_path / "blog.json"
    run("blog_export", "--output", str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["articles"][0]["slug"] == article.slug
    Article.objects.all().delete()
    Tag.objects.all().delete()
    Category.objects.all().delete()
    run("blog_import", str(path))
    run("blog_import", str(path))
    imported = Article.objects.get(slug=article.slug)
    assert Article.objects.count() == 1 and imported.tags.count() == 1
    assert imported.comment_count == 1 and imported.announced_at is not None
    assert Category.objects.get(slug=child.slug).parent.slug == parent_slug
    assert "articles" in run("blog_export")


def test_import_rejects_garbage(tmp_path):
    from django.core.management.base import CommandError

    path = tmp_path / "bad.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(CommandError):
        run("blog_import", str(path))


def test_recount(article, reader):
    Comment.objects.create(article=article, user=reader, content="x", status="approved")
    Article.objects.update(comment_count=99, reaction_count=5)
    run("blog_recount")
    article.refresh_from_db()
    assert (article.comment_count, article.reaction_count) == (1, 0)


def test_setup_roles():
    from django.contrib.auth.models import Group

    run("blog_setup_roles")
    run("blog_setup_roles")
    editors = Group.objects.get(name="Blog editors")
    assert editors.permissions.filter(codename="publish_article").exists()


def test_seed_is_idempotent():
    run("blog_seed", "--articles", "3")
    run("blog_seed", "--articles", "3")
    assert Article.objects.count() == 3
    assert Article.objects.published().count() == 3


def test_cleanup(article, reader, draft):
    Comment.objects.create(article=article, user=reader, content="spam", status="spam")
    Comment.objects.update(updated_at="2000-01-01T00:00:00Z")
    Article.objects.filter(pk=draft.pk).update(updated_at="2000-01-01T00:00:00Z")
    assert "Dry run" in run("blog_cleanup", "--dry-run")
    run("blog_cleanup")
    assert not Comment.objects.exists() and Article.objects.filter(pk=draft.pk).exists()
    run("blog_cleanup", "--drafts-days", "30")
    assert not Article.objects.filter(pk=draft.pk).exists()


def test_maintenance(settings, author):
    IdempotencyRecord.objects.create(scope="s", key="k", method="POST", path="/", fingerprint="f")
    Subscriber.objects.create(email="old@example.com")
    Subscriber.objects.update(created_at="2000-01-01T00:00:00Z")
    IdempotencyRecord.objects.update(created_at="2000-01-01T00:00:00Z")
    out = run("blog_maintenance")
    assert "idempotency_purged: 1" in out and "subscribers_purged: 1" in out
    assert tasks.run_maintenance()["announced"] == 0


# --- feature flags, admin and checks ----------------------------------------------


@pytest.mark.parametrize(
    "feature,url",
    [
        ("comments", "/comments/"),
        ("media", "/media/"),
        ("bookmarks", "/bookmarks/"),
        ("notifications", "/notifications/"),
        ("search", "/search/?q=hello"),
        ("series", "/series/"),
    ],
)
def test_disabled_features_return_404(settings, editor, feature, url):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "FEATURES": {feature: False}}
    assert client_for(editor).get(f"{API}{url}").status_code == 404


@pytest.mark.parametrize("feature,path", [("reactions", "reactions/like/"), ("bookmarks", "bookmark/")])
def test_disabled_engagement(settings, reader, article, feature, path):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "FEATURES": {feature: False}}
    assert client_for(reader).put(f"{API}/articles/{article.slug}/{path}").status_code == 404


def test_disabled_comments_close_article_threads(settings, reader, article):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "FEATURES": {"comments": False}}
    assert client_for(reader).get(f"{API}/articles/{article.slug}/comments/").status_code == 404


def test_api_root_lists_endpoints(anon):
    root = anon.get(f"{API}/").data
    assert {"articles", "authors", "categories", "tags", "comments", "media", "notifications"} <= set(root)


def test_settings_merge_and_reload(settings):
    assert blog_settings.COMMENTS["max_depth"] == 4
    settings.FLEX_BLOG = {"COMMENTS": {"max_depth": 1}}
    assert blog_settings.COMMENTS["max_depth"] == 1
    assert blog_settings.COMMENTS["min_length"] == 2  # deep merge keeps defaults
    with pytest.raises(AttributeError):
        blog_settings.NOPE  # noqa: B018


def test_system_checks():
    from flex_blog.checks import check_deploy, check_settings

    with override_settings(FLEX_BLOG={"TYPO": 1, "FEATURES": {"nope": True}, "TASKS": {"backend": "rq"},
                                      "SEARCH": {"backend": "missing.Backend"}, "COMMENTS": {"moderation": "maybe"}}):
        ids = {e.id for e in check_settings(None)}
    assert {"flex_blog.W001", "flex_blog.W002", "flex_blog.E003", "flex_blog.E005", "flex_blog.E006"} <= ids
    locmem = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    with override_settings(CACHES=locmem):
        assert "flex_blog.W010" in {w.id for w in check_deploy(None)}
    redis = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": "redis://localhost:6379"}}
    with override_settings(CACHES=redis):
        assert "flex_blog.W010" not in {w.id for w in check_deploy(None)}
    assert check_settings(None) == []


def test_admin_pages_render(client, admin_user, article, reader):
    Comment.objects.create(article=article, user=reader, content="hello", status="pending")
    client.force_login(admin_user)
    for model in ("article", "author", "category", "tag", "series", "comment", "media", "subscriber",
                  "notification", "webhookendpoint", "webhookdelivery"):
        assert client.get(f"/admin/flex_blog/{model}/").status_code == 200, model
    assert client.get(f"/admin/flex_blog/article/{article.pk}/change/").status_code == 200
    assert client.get("/admin/flex_blog/article/add/").status_code == 200


def test_admin_actions_use_services(client, admin_user, author, reader, article):
    draft = make_article(author, title="Admin draft", status=Article.Status.DRAFT)
    pending = Comment.objects.create(article=article, user=reader, content="hello", status="pending")
    client.force_login(admin_user)
    client.post("/admin/flex_blog/article/", {"action": "publish", "_selected_action": [str(draft.pk)]})
    draft.refresh_from_db()
    assert draft.is_live and draft.announced_at is not None
    client.post("/admin/flex_blog/comment/", {"action": "approve", "_selected_action": [str(pending.pk)]})
    article.refresh_from_db()
    assert article.comment_count == 1

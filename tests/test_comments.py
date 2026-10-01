from datetime import timedelta

import pytest
from django.utils import timezone

from flex_blog.models import Article, Comment

from .conftest import API, client_for, make_article, make_user

pytestmark = pytest.mark.django_db


def post_comment(client, article, **data):
    data.setdefault("content", "A thoughtful comment")
    return client.post(f"{API}/articles/{article.slug}/comments/", data)


def test_first_time_moderation(reader, article):
    client = client_for(reader)
    first = post_comment(client, article)
    assert first.status_code == 201 and first.data["status"] == "pending"
    article.refresh_from_db()
    assert article.comment_count == 0
    # pending comments are visible to their author only
    assert client.get(f"{API}/articles/{article.slug}/comments/").data["count"] == 1
    assert client_for().get(f"{API}/articles/{article.slug}/comments/").data["count"] == 0
    Comment.objects.update(status="approved")
    second = post_comment(client, article)
    assert second.data["status"] == "approved"
    article.refresh_from_db()
    assert article.comment_count == 1  # only the auto-approved one was counted live


@pytest.mark.parametrize("mode,expected", [("none", "approved"), ("all", "pending"), ("anonymous", "approved")])
def test_moderation_modes(settings, reader, article, mode, expected):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "COMMENTS": {"moderation": mode}}
    assert post_comment(client_for(reader), article).data["status"] == expected


def test_moderators_are_auto_approved(moderator, article):
    assert post_comment(client_for(moderator), article).data["status"] == "approved"


def test_anonymous_comments(settings, anon, article):
    assert post_comment(anon, article).status_code in (401, 403)
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "COMMENTS": {"allow_anonymous": True}}
    assert post_comment(anon, article).status_code == 400  # name + email required
    response = post_comment(anon, article, author_name="Chidi", author_email="CHIDI@example.com", author_url="https://chidi.ng")
    assert response.status_code == 201 and response.data["status"] == "pending"
    comment = Comment.objects.get()
    assert comment.author_email == "chidi@example.com"
    assert response.data["author"]["name"] == "Chidi" and response.data["author"]["is_guest"] is True


def test_honeypot(reader, article):
    assert post_comment(client_for(reader), article, website_hp="http://spam").status_code == 400


def test_content_rules(settings, reader, article):
    client = client_for(reader)
    assert post_comment(client, article, content="x").status_code == 400
    assert post_comment(client, article, content="see https://a.com https://b.com https://c.com https://d.com").status_code == 400
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "COMMENTS": {"blocked_words": ["casino"]}}
    assert post_comment(client, article, content="Best CASINO bonus").status_code == 400


def test_spam_checker_hook(settings, reader, article):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "COMMENTS": {"spam_checker": "tests.hooks.always_spam"}}
    assert post_comment(client_for(reader), article).data["status"] == "spam"
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "COMMENTS": {"spam_checker": "tests.hooks.broken_checker", "moderation": "none"}}
    assert post_comment(client_for(reader), article).data["status"] == "pending"


def test_closed_comments(settings, reader, author):
    closed = make_article(author, title="Closed", allow_comments=False)
    assert post_comment(client_for(reader), closed).status_code == 403
    old = make_article(author, title="Old", published_at=timezone.now() - timedelta(days=100))
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "COMMENTS": {"close_after_days": 30}}
    assert post_comment(client_for(reader), old).status_code == 403
    draft = make_article(author, title="Draft", status=Article.Status.DRAFT)
    assert post_comment(client_for(draft.author.user), draft).status_code == 403


def test_threading_and_depth(settings, moderator, article):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "COMMENTS": {"max_depth": 1}}
    client = client_for(moderator)
    root = post_comment(client, article).data["id"]
    reply = post_comment(client, article, parent=root)
    assert reply.status_code == 201 and reply.data["depth"] == 1
    too_deep = post_comment(client, article, parent=reply.data["id"])
    assert too_deep.status_code == 400
    other = make_article(article.author, title="Other")
    assert post_comment(client, other, parent=root).status_code == 400
    top = client.get(f"{API}/articles/{article.slug}/comments/?parent=none").data
    assert top["count"] == 1
    assert client.get(f"{API}/comments/?parent={root}").data["count"] == 1


def test_create_via_comments_endpoint(reader, article):
    client = client_for(reader)
    assert client.post(f"{API}/comments/", {"content": "hi there"}).status_code == 400
    assert client.post(f"{API}/comments/", {"article": "missing", "content": "hi there"}).status_code == 400
    assert client.post(f"{API}/comments/", {"article": article.slug, "content": "hi there"}).status_code == 201


def test_edit_window_and_ownership(settings, reader, article):
    client = client_for(reader)
    comment_id = post_comment(client, article).data["id"]
    edited = client.patch(f"{API}/comments/{comment_id}/", {"content": "Edited text"})
    assert edited.status_code == 200 and edited.data["is_edited"] is True
    assert client_for(make_user("stranger")).patch(f"{API}/comments/{comment_id}/", {"content": "Hijack"}).status_code in (403, 404)
    Comment.objects.filter(pk=comment_id).update(created_at=timezone.now() - timedelta(hours=1))
    assert client.patch(f"{API}/comments/{comment_id}/", {"content": "Too late"}).status_code == 403


def test_remove_is_soft_and_updates_counter(moderator, article):
    client = client_for(moderator)
    comment_id = post_comment(client, article).data["id"]
    article.refresh_from_db()
    assert article.comment_count == 1
    assert client.delete(f"{API}/comments/{comment_id}/").status_code == 204
    assert client.delete(f"{API}/comments/{comment_id}/").status_code == 204  # idempotent
    article.refresh_from_db()
    assert article.comment_count == 0
    data = client.get(f"{API}/comments/{comment_id}/").data
    assert data["is_removed"] is True and data["content_html"] == ""


def test_moderation_actions(reader, moderator, article):
    comment_id = post_comment(client_for(reader), article).data["id"]
    mod = client_for(moderator)
    assert client_for(reader).post(f"{API}/comments/{comment_id}/approve/").status_code == 403
    assert mod.get(f"{API}/comments/?status=pending").data["count"] == 1
    assert mod.post(f"{API}/comments/{comment_id}/approve/").data["status"] == "approved"
    assert mod.post(f"{API}/comments/{comment_id}/approve/").status_code == 200  # idempotent
    article.refresh_from_db()
    assert article.comment_count == 1
    assert mod.post(f"{API}/comments/{comment_id}/spam/").data["status"] == "spam"
    article.refresh_from_db()
    assert article.comment_count == 0
    assert mod.post(f"{API}/comments/{comment_id}/reject/").data["status"] == "rejected"
    assert "email" in mod.get(f"{API}/comments/{comment_id}/").data["author"]


def test_flagging(settings, moderator, article):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "COMMENTS": {"flag_threshold": 2}}
    comment_id = post_comment(client_for(moderator), article).data["id"]
    first, second = make_user("f1"), make_user("f2")
    response = client_for(first).post(f"{API}/comments/{comment_id}/flag/", {"reason": "rude"})
    assert response.data == {"flagged": True, "created": True}
    assert client_for(first).post(f"{API}/comments/{comment_id}/flag/").data["created"] is False
    client_for(second).post(f"{API}/comments/{comment_id}/flag/")
    assert Comment.objects.get(pk=comment_id).status == "pending"
    assert client_for().post(f"{API}/comments/{comment_id}/flag/").status_code in (401, 403, 404)


def test_store_ip_optional(settings, reader, article):
    post_comment(client_for(reader), article)
    assert Comment.objects.get().ip_address is None
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "COMMENTS": {"store_ip_address": True}}
    post_comment(client_for(reader), article, content="Another one")
    assert Comment.objects.exclude(ip_address=None).get().ip_address == "127.0.0.1"


def test_unlisted_comments_not_in_global_feed(moderator, reader, author):
    hidden = make_article(author, title="Hidden", visibility=Article.Visibility.UNLISTED)
    post_comment(client_for(moderator), hidden)
    assert client_for(reader).get(f"{API}/comments/").data["count"] == 0
    assert client_for(reader).get(f"{API}/articles/{hidden.slug}/comments/").data["count"] == 1

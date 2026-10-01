import pytest

from flex_blog.models import Article, Bookmark, Reaction

from .conftest import API, client_for, make_article

pytestmark = pytest.mark.django_db


def test_reactions_are_idempotent(reader, article):
    client = client_for(reader)
    url = f"{API}/articles/{article.slug}/reactions/like/"
    assert client.put(url).data["reaction_count"] == 1
    assert client.put(url).data["reaction_count"] == 1
    assert Reaction.objects.count() == 1
    detail = client.get(f"{API}/articles/{article.slug}/").data
    assert detail["viewer"]["reactions"] == ["like"] and detail["reactions"] == {"like": 1}
    assert client.delete(url).data == {"kind": "like", "reacted": False, "reaction_count": 0, "reactions": {}}
    assert client.delete(url).data["reaction_count"] == 0


def test_reaction_kinds_configurable(settings, reader, article):
    client = client_for(reader)
    assert client.put(f"{API}/articles/{article.slug}/reactions/fire/").status_code == 400
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "REACTIONS": {"kinds": ["like", "fire"]}}
    assert client.put(f"{API}/articles/{article.slug}/reactions/fire/").status_code == 200


def test_reactions_need_login_and_live_article(anon, reader, draft, article):
    assert anon.put(f"{API}/articles/{article.slug}/reactions/like/").status_code in (401, 403)
    assert client_for(draft.author.user).put(f"{API}/articles/{draft.slug}/reactions/like/").status_code == 404


def test_bookmarks(reader, article, author):
    client = client_for(reader)
    assert client.put(f"{API}/articles/{article.slug}/bookmark/").data == {"bookmarked": True}
    client.put(f"{API}/articles/{article.slug}/bookmark/")
    assert Bookmark.objects.count() == 1
    gone = make_article(author, title="Soon unpublished")
    client.put(f"{API}/articles/{gone.slug}/bookmark/")
    Article.objects.filter(pk=gone.pk).update(status=Article.Status.DRAFT)
    listing = client.get(f"{API}/bookmarks/").data
    assert [b["article"]["slug"] for b in listing["results"]] == [article.slug]
    assert client.get(f"{API}/articles/{article.slug}/").data["viewer"]["bookmarked"] is True
    assert client.delete(f"{API}/articles/{article.slug}/bookmark/").data == {"bookmarked": False}
    assert client_for().get(f"{API}/bookmarks/").status_code in (401, 403)


def test_counters_consistent_under_repeated_toggles(reader, article):
    client = client_for(reader)
    url = f"{API}/articles/{article.slug}/reactions/like/"
    for _ in range(5):
        client.put(url)
        client.delete(url)
    client.put(url)
    article.refresh_from_db()
    assert article.reaction_count == Reaction.objects.filter(article=article).count() == 1

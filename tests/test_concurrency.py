"""
Race handling.

The deterministic tests force each race branch (unique-constraint loser
paths). ``test_parallel_*`` run real threads and need PostgreSQL
(FLEX_BLOG_TEST_DB=postgres); SQLite serialises writers, so they are skipped there.
"""

import threading

import pytest
from django.db import connection, connections

from flex_blog.models import Article, Reaction, Tag
from flex_blog.models import base as base_module
from flex_blog.services import articles as article_service
from flex_blog.services import engagement

from .conftest import make_article, make_user

needs_postgres = pytest.mark.skipif(connection.vendor != "postgresql", reason="needs PostgreSQL for real parallel writes")


@pytest.mark.django_db
def test_slug_race_retries(monkeypatch, author):
    taken = make_article(author, title="Taken")
    calls = {"n": 0}
    original = base_module.unique_slugify

    def stale_check(instance, value, **kwargs):
        calls["n"] += 1
        # First attempt behaves as if it read the table before "Taken" existed.
        return taken.slug if calls["n"] == 1 else original(instance, value, **kwargs)

    monkeypatch.setattr(base_module, "unique_slugify", stale_check)
    article = make_article(author, title="Taken")
    assert article.slug != taken.slug and article.slug.startswith("taken-")
    assert calls["n"] == 2


@pytest.mark.django_db
def test_tag_creation_race(monkeypatch, article):
    Tag.objects.create(name="Lagos")
    real_filter = Tag.objects.filter
    state = {"first": True}

    def blind_filter(*args, **kwargs):
        qs = real_filter(*args, **kwargs)
        if state["first"]:
            state["first"] = False
            return qs.none()  # pretend the tag did not exist yet
        return qs

    monkeypatch.setattr(Tag.objects, "filter", blind_filter)
    article_service.set_tags(article, ["Lagos"])
    assert list(article.tags.values_list("name", flat=True)) == ["Lagos"]
    assert Tag.objects.filter(name="Lagos").count() == 1


@pytest.mark.django_db
def test_duplicate_reaction_insert_is_swallowed(reader, article):
    engagement.add_reaction(article, reader)
    reaction, created = engagement.add_reaction(article, reader)
    assert created is False and reaction.pk
    article.refresh_from_db()
    assert article.reaction_count == 1


def _run_parallel(target, workers=8):
    barrier = threading.Barrier(workers)
    errors = []

    def wrapped(i):
        try:
            barrier.wait()
            target(i)
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=wrapped, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors


@needs_postgres
@pytest.mark.django_db(transaction=True)
def test_parallel_reactions_count_exactly(author_user):
    from flex_blog.models import Author

    article = make_article(Author.for_user(author_user))
    users = [make_user(f"p{i}") for i in range(8)]
    _run_parallel(lambda i: [engagement.add_reaction(article, users[i]) for _ in range(3)])
    article.refresh_from_db()
    assert Reaction.objects.filter(article=article).count() == article.reaction_count == 8


@needs_postgres
@pytest.mark.django_db(transaction=True)
def test_parallel_announce_fires_once(author_user):
    from flex_blog.models import Author

    article = make_article(Author.for_user(author_user), status=Article.Status.DRAFT)
    Article.objects.filter(pk=article.pk).update(status=Article.Status.PUBLISHED, published_at=article.created_at)
    results = []
    _run_parallel(lambda i: results.append(article_service.announce(article.pk)))
    assert results.count(True) == 1


@needs_postgres
@pytest.mark.django_db(transaction=True)
def test_parallel_same_title_unique_slugs(author_user):
    from flex_blog.models import Author

    author = Author.for_user(author_user)
    _run_parallel(lambda i: make_article(author, title="Breaking news"))
    slugs = list(Article.objects.values_list("slug", flat=True))
    assert len(slugs) == len(set(slugs)) == 8


@needs_postgres
@pytest.mark.django_db
def test_postgres_full_text_search(settings, author):
    settings.FLEX_BLOG = {**settings.FLEX_BLOG, "SEARCH": {"backend": "flex_blog.search.PostgresSearchBackend"}}
    from flex_blog.search import search_articles

    make_article(author, title="Running a marathon", content="Training plans for runners")
    make_article(author, title="Cooking", content="Nothing about that")
    results = list(search_articles(Article.objects.listed(), "run"))
    assert [a.title for a in results] == ["Running a marathon"]

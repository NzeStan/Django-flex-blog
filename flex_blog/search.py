"""
Pluggable article search.

* ``DatabaseSearchBackend`` (default): works on every database. Matches all
  words across title, subtitle, summary and content; title hits rank first.
* ``PostgresSearchBackend``: weighted full-text search with ranking (needs
  PostgreSQL and ``django.contrib.postgres`` in INSTALLED_APPS).

Write your own (Elasticsearch, Meilisearch, Typesense...) by subclassing
``BaseSearchBackend`` and pointing FLEX_BLOG["SEARCH"]["backend"] at it.
Return a queryset of articles; flex_blog paginates and serialises it.
Keep your index fresh by listening to ``flex_blog.signals``.
"""

from functools import reduce
from operator import and_

from django.db.models import Case, IntegerField, Q, Value, When

from flex_blog.conf import blog_settings

MAX_TERMS = 8


class BaseSearchBackend:
    def search(self, queryset, query):  # pragma: no cover - interface
        raise NotImplementedError


class DatabaseSearchBackend(BaseSearchBackend):
    fields = ("title", "subtitle", "summary", "content")

    def search(self, queryset, query):
        terms = [t for t in query.split() if t][:MAX_TERMS]
        if not terms:
            return queryset.none()
        per_term = [reduce(lambda a, b: a | b, (Q(**{f"{f}__icontains": t}) for f in self.fields)) for t in terms]
        title_hit = reduce(and_, (Q(title__icontains=t) for t in terms))
        return (
            queryset.filter(reduce(and_, per_term))
            .annotate(search_rank=Case(When(title_hit, then=Value(2)), default=Value(1), output_field=IntegerField()))
            .order_by("-search_rank", "-published_at")
        )


class PostgresSearchBackend(BaseSearchBackend):
    def search(self, queryset, query):
        from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

        config = blog_settings.SEARCH["config"]
        vector = (
            SearchVector("title", weight="A", config=config)
            + SearchVector("subtitle", "summary", weight="B", config=config)
            + SearchVector("content", weight="C", config=config)
        )
        search_query = SearchQuery(query, search_type="websearch", config=config)
        return (
            queryset.annotate(search_rank=SearchRank(vector, search_query))
            .filter(search_rank__gt=0)
            .order_by("-search_rank", "-published_at")
        )


def get_backend():
    return blog_settings.import_from(blog_settings.SEARCH["backend"])()


def search_articles(queryset, query):
    query = (query or "").strip()[:200]
    if not query:
        return queryset.none()
    return get_backend().search(queryset, query)

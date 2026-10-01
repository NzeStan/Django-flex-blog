import uuid

import django_filters

from flex_blog.models import Article, Category, Comment


class CharInFilter(django_filters.BaseInFilter, django_filters.CharFilter):
    pass


class ArticleFilter(django_filters.FilterSet):
    category = django_filters.CharFilter(method="filter_category", help_text="Category slug (includes sub-categories).")
    tag = CharInFilter(method="filter_tags", help_text="Tag slug(s), comma separated: articles having any of them.")
    author = django_filters.CharFilter(field_name="author__slug")
    series = django_filters.CharFilter(field_name="series__slug")
    status = django_filters.ChoiceFilter(choices=Article.Status.choices)
    visibility = django_filters.ChoiceFilter(choices=Article.Visibility.choices)
    is_featured = django_filters.BooleanFilter()
    is_pinned = django_filters.BooleanFilter()
    language = django_filters.CharFilter()
    year = django_filters.NumberFilter(field_name="published_at", lookup_expr="year")
    month = django_filters.NumberFilter(field_name="published_at", lookup_expr="month")
    published_after = django_filters.IsoDateTimeFilter(field_name="published_at", lookup_expr="gte")
    published_before = django_filters.IsoDateTimeFilter(field_name="published_at", lookup_expr="lte")

    class Meta:
        model = Article
        fields = []

    def filter_category(self, queryset, name, value):
        category = Category.objects.filter(slug=value).first()
        if category is None:
            return queryset.none()
        return queryset.filter(categories__in=category.get_descendant_ids()).distinct()

    def filter_tags(self, queryset, name, value):
        slugs = [v for v in value if v][:10]
        return queryset.filter(tags__slug__in=slugs).distinct() if slugs else queryset


class CommentFilter(django_filters.FilterSet):
    article = django_filters.CharFilter(field_name="article__slug")
    parent = django_filters.CharFilter(method="filter_parent", help_text='Comment id, or "none" for top-level comments.')
    status = django_filters.ChoiceFilter(choices=Comment.Status.choices)

    class Meta:
        model = Comment
        fields = []

    def filter_parent(self, queryset, name, value):
        if value in ("none", "null", ""):
            return queryset.filter(parent__isnull=True)
        try:
            return queryset.filter(parent_id=uuid.UUID(value))
        except ValueError:
            return queryset.none()


class CategoryFilter(django_filters.FilterSet):
    parent = django_filters.CharFilter(method="filter_parent", help_text='Parent slug, or "none" for top-level.')

    class Meta:
        model = Category
        fields = []

    def filter_parent(self, queryset, name, value):
        if value in ("none", "null", ""):
            return queryset.filter(parent__isnull=True)
        return queryset.filter(parent__slug=value)


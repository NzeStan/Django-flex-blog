import django_filters
from flex_blog.registry import model_registry


class ArticleFilter(django_filters.FilterSet):
    """Filter for articles."""
    
    title = django_filters.CharFilter(lookup_expr='icontains')
    content = django_filters.CharFilter(lookup_expr='icontains')
    created_after = django_filters.DateFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateFilter(field_name='created_at', lookup_expr='lte')
    published_after = django_filters.DateFilter(field_name='published_at', lookup_expr='gte')
    published_before = django_filters.DateFilter(field_name='published_at', lookup_expr='lte')
    category = django_filters.CharFilter(field_name='categories__slug')
    tag = django_filters.CharFilter(field_name='tags__slug')
    
    class Meta:
        model = model_registry.get_model('article')
        fields = [
            'status', 'author', 'is_featured', 'allow_comments',
        ]


class AuthorFilter(django_filters.FilterSet):
    """Filter for authors."""
    
    display_name = django_filters.CharFilter(lookup_expr='icontains')
    bio = django_filters.CharFilter(lookup_expr='icontains')
    
    class Meta:
        model = model_registry.get_model('author')
        fields = ['is_active']


class CategoryFilter(django_filters.FilterSet):
    """Filter for categories."""
    
    name = django_filters.CharFilter(lookup_expr='icontains')
    description = django_filters.CharFilter(lookup_expr='icontains')
    
    class Meta:
        model = model_registry.get_model('category')
        fields = ['parent', 'is_active']


class TagFilter(django_filters.FilterSet):
    """Filter for tags."""
    
    name = django_filters.CharFilter(lookup_expr='icontains')
    description = django_filters.CharFilter(lookup_expr='icontains')
    
    class Meta:
        model = model_registry.get_model('tag')
        fields = ['name']


class CommentFilter(django_filters.FilterSet):
    """Filter for comments."""
    
    content = django_filters.CharFilter(lookup_expr='icontains')
    author_name = django_filters.CharFilter(lookup_expr='icontains')
    created_after = django_filters.DateFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateFilter(field_name='created_at', lookup_expr='lte')
    
    class Meta:
        model = model_registry.get_model('comment')
        fields = ['article', 'user', 'is_approved']


class MediaFilter(django_filters.FilterSet):
    """Filter for media."""
    
    title = django_filters.CharFilter(lookup_expr='icontains')
    description = django_filters.CharFilter(lookup_expr='icontains')
    type = django_filters.CharFilter()
    created_after = django_filters.DateFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateFilter(field_name='created_at', lookup_expr='lte')
    
    class Meta:
        model = model_registry.get_model('media')
        fields = ['type']

from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from flex_blog.registry import model_registry
from flex_blog.serializers.tag import TagSerializer
from flex_blog.serializers.article import ArticleSerializer
from flex_blog.permissions import IsAdminOrReadOnly


class TagViewSet(viewsets.ModelViewSet):
    """ViewSet for tags."""
    
    serializer_class = TagSerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    def get_queryset(self):
        """Get the queryset for the view."""
        Tag = model_registry.get_model('tag')
        return Tag.objects.all()
    
    @action(detail=True, methods=['get'])
    def articles(self, request, slug=None):
        """Get articles with a tag."""
        tag = self.get_object()
        Article = model_registry.get_model('article')
        
        # Filter for published articles only for non-staff users
        if request.user.is_staff:
            articles = Article.objects.filter(tags=tag)
        else:
            articles = Article.objects.filter(
                tags=tag,
                status='published'
            )
            
        # Paginate results
        page = self.paginate_queryset(articles)
        if page is not None:
            serializer = ArticleSerializer(
                page, 
                many=True,
                context={'request': request}
            )
            return self.get_paginated_response(serializer.data)
            
        serializer = ArticleSerializer(
            articles, 
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)

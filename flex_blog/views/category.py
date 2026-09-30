from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from flex_blog.registry import model_registry
from flex_blog.serializers.category import CategorySerializer, CategoryDetailSerializer
from flex_blog.serializers.article import ArticleSerializer
from flex_blog.permissions import IsAdminOrReadOnly


class CategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for categories."""
    
    serializer_class = CategorySerializer
    detail_serializer_class = CategoryDetailSerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]
    filterset_fields = ['parent', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'order']
    ordering = ['order', 'name']
    
    def get_queryset(self):
        """Get the queryset for the view."""
        Category = model_registry.get_model('category')
        queryset = Category.objects.all()
        
        # Filter for active categories only for non-staff users
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
            
        return queryset
    
    @action(detail=True, methods=['get'])
    def articles(self, request, slug=None):
        """Get articles in a category."""
        category = self.get_object()
        Article = model_registry.get_model('article')
        
        # Filter for published articles only for non-staff users
        if request.user.is_staff:
            articles = Article.objects.filter(categories=category)
        else:
            articles = Article.objects.filter(
                categories=category,
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

from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from flex_blog.registry import model_registry
from flex_blog.serializers.author import AuthorSerializer, AuthorDetailSerializer
from flex_blog.serializers.article import ArticleSerializer
from flex_blog.permissions import IsOwnerOrReadOnly


class AuthorViewSet(viewsets.ModelViewSet):
    """ViewSet for authors."""
    
    serializer_class = AuthorSerializer
    detail_serializer_class = AuthorDetailSerializer
    permission_classes = [IsOwnerOrReadOnly]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]
    filterset_fields = ['is_active']
    search_fields = ['display_name', 'bio']
    ordering_fields = ['display_name', 'created_at']
    ordering = ['display_name']
    
    def get_queryset(self):
        """Get the queryset for the view."""
        Author = model_registry.get_model('author')
        return Author.objects.all()
    
    @action(detail=True, methods=['get'])
    def articles(self, request, pk=None):
        """Get articles by an author."""
        author = self.get_object()
        Article = model_registry.get_model('article')
        
        # Filter for published articles only for non-staff users
        if request.user.is_staff:
            articles = Article.objects.filter(author=author)
        else:
            articles = Article.objects.filter(
                author=author,
                status='published'
            )
            
        serializer = ArticleSerializer(
            articles, 
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
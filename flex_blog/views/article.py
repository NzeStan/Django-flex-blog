from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
from flex_blog.registry import model_registry
from flex_blog.serializers.article import (
    ArticleSerializer, ArticleDetailSerializer, ArticleCreateUpdateSerializer
)
from flex_blog.serializers.comment import CommentSerializer, CommentCreateSerializer
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from flex_blog.permissions import IsAuthorOrReadOnly


class ArticleViewSet(viewsets.ModelViewSet):
    """ViewSet for articles."""
    
    serializer_class = ArticleSerializer
    detail_serializer_class = ArticleDetailSerializer
    create_update_serializer_class = ArticleCreateUpdateSerializer
    permission_classes = [IsAuthorOrReadOnly]
    lookup_field = 'slug'
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]
    filterset_fields = ['status', 'author', 'categories', 'tags', 'is_featured']
    search_fields = ['title', 'content', 'summary']
    ordering_fields = ['published_at', 'created_at', 'title', 'views']
    ordering = ['-published_at']
    
    def get_queryset(self):
        """Get the queryset for the view."""
        Article = model_registry.get_model('article')
        queryset = Article.objects.all()
        
        # Filter for published articles only for non-staff users
        if not self.request.user.is_staff:
            queryset = queryset.filter(status='published')
            
        return queryset
    
    def retrieve(self, request, *args, **kwargs):
        """Retrieve an article and increment its view count."""
        instance = self.get_object()
        instance.increment_views()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def comments(self, request, slug=None):
        """Get comments for an article."""
        article = self.get_object()
        Comment = model_registry.get_model('comment')
        
        # Get approved comments only for non-staff users
        if request.user.is_staff:
            comments = Comment.objects.filter(article=article)
        else:
            comments = Comment.objects.filter(article=article, is_approved=True)
            
        serializer = CommentSerializer(
            comments, 
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def add_comment(self, request, slug=None):
        """Add a comment to an article."""
        article = self.get_object()
        
        # Check if comments are allowed
        if not article.allow_comments:
            return Response(
                {'detail': _('Comments are not allowed for this article.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Add article to the data
        data = request.data.copy()
        data['article'] = article.pk
        
        serializer = CommentCreateSerializer(
            data=data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED
            )
        
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=True, methods=['post'])
    def publish(self, request, slug=None):
        """Publish an article."""
        article = self.get_object()
        
        # Check if article is already published
        if article.status == 'published':
            return Response(
                {'detail': _('This article is already published.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update status and published_at
        article.status = 'published'
        article.published_at = timezone.now()
        article.save()
        
        serializer = self.get_serializer(article)
        return Response(serializer.data)

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from flex_blog.registry import model_registry
from flex_blog.serializers.article import ArticleSerializer
from flex_blog.serializers.author import AuthorSerializer
from flex_blog.serializers.category import CategorySerializer
from flex_blog.serializers.tag import TagSerializer
from django.db.models import Q


class SearchView(APIView):
    """View for searching across all blog models."""
    
    def get(self, request, format=None):
        """Search across all blog models."""
        query = request.query_params.get('q', '')
        
        if not query:
            return Response(
                {'detail': 'Please provide a search query with the "q" parameter.'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Get models
        Article = model_registry.get_model('article')
        Author = model_registry.get_model('author')
        Category = model_registry.get_model('category')
        Tag = model_registry.get_model('tag')
        
        # Search in each model
        articles = Article.objects.filter(
            Q(title__icontains=query) | 
            Q(content__icontains=query) |
            Q(summary__icontains=query)
        ).filter(status='published')
        
        authors = Author.objects.filter(
            Q(display_name__icontains=query) |
            Q(bio__icontains=query)
        ).filter(is_active=True)
        
        categories = Category.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        ).filter(is_active=True)
        
        tags = Tag.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )
        
        # Serialize the results
        article_serializer = ArticleSerializer(
            articles[:10], 
            many=True,
            context={'request': request}
        )
        
        author_serializer = AuthorSerializer(
            authors[:5], 
            many=True,
            context={'request': request}
        )
        
        category_serializer = CategorySerializer(
            categories[:5], 
            many=True,
            context={'request': request}
        )
        
        tag_serializer = TagSerializer(
            tags[:5], 
            many=True,
            context={'request': request}
        )
        
        # Return the results
        return Response({
            'articles': article_serializer.data,
            'authors': author_serializer.data,
            'categories': category_serializer.data,
            'tags': tag_serializer.data,
            'count': {
                'articles': articles.count(),
                'authors': authors.count(),
                'categories': categories.count(),
                'tags': tags.count(),
                'total': articles.count() + authors.count() + categories.count() + tags.count()
            }
        })

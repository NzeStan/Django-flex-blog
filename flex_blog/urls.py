from django.urls import path, include
from rest_framework.routers import DefaultRouter
from flex_blog.views import (
    ArticleViewSet, AuthorViewSet, CategoryViewSet,
    CommentViewSet, MediaViewSet, TagViewSet, SearchView
)
from flex_blog.conf import settings

app_name = 'flex_blog'

# Create a router and register our viewsets
router = DefaultRouter()
router.register(r'articles', ArticleViewSet, basename='article')
router.register(r'authors', AuthorViewSet, basename='author')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'comments', CommentViewSet, basename='comment')
router.register(r'media', MediaViewSet, basename='media')
router.register(r'tags', TagViewSet, basename='tag')

# URL patterns
urlpatterns = [
    path('', include(router.urls)),
    path('search/', SearchView.as_view(), name='search'),
]
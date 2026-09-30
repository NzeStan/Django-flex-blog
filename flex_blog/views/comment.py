from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from flex_blog.registry import model_registry
from flex_blog.serializers.comment import CommentSerializer, CommentCreateSerializer
from flex_blog.permissions import IsOwnerModeratorOrReadOnly


class CommentViewSet(viewsets.ModelViewSet):
    """ViewSet for comments."""
    
    serializer_class = CommentSerializer
    create_serializer_class = CommentCreateSerializer
    permission_classes = [IsOwnerModeratorOrReadOnly]
    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter
    ]
    filterset_fields = ['article', 'user', 'is_approved']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Get the queryset for the view."""
        Comment = model_registry.get_model('comment')
        queryset = Comment.objects.all()
        
        # Filter for approved comments only for non-staff users
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_approved=True)
            
        return queryset
    
    def get_serializer_class(self):
        """Get the serializer class for the action."""
        if self.action == 'create':
            return CommentCreateSerializer
        return CommentSerializer
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a comment."""
        comment = self.get_object()
        
        # Check if comment is already approved
        if comment.is_approved:
            return Response(
                {'detail': 'This comment is already approved.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Approve the comment
        comment.is_approved = True
        comment.save()
        
        serializer = self.get_serializer(comment)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a comment."""
        comment = self.get_object()
        
        # Delete the comment
        comment.delete()
        
        return Response(
            {'detail': 'Comment has been rejected and deleted.'},
            status=status.HTTP_204_NO_CONTENT
        )
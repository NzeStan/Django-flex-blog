from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed for any request
        if request.method in permissions.SAFE_METHODS:
            return True
            
        # Write permissions are only allowed to the owner
        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'author') and hasattr(obj.author, 'user'):
            return obj.author.user == request.user
            
        # If we can't determine the owner, deny permission
        return False


class IsAuthorOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow authors of an article to edit it.
    """
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed for any request
        if request.method in permissions.SAFE_METHODS:
            return True
            
        # Staff users can edit anything
        if request.user.is_staff:
            return True
            
        # Write permissions are only allowed to the author
        if hasattr(obj, 'author') and hasattr(obj.author, 'user'):
            return obj.author.user == request.user
            
        # If we can't determine the author, deny permission
        return False


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow admins to edit objects.
    """
    
    def has_permission(self, request, view):
        # Read permissions are allowed for any request
        if request.method in permissions.SAFE_METHODS:
            return True
            
        # Write permissions are only allowed to staff users
        return request.user.is_staff


class IsOwnerModeratorOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners or moderators to edit comments.
    """
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed for any request
        if request.method in permissions.SAFE_METHODS:
            return True
            
        # Staff users can edit anything
        if request.user.is_staff:
            return True
            
        # Write permissions are only allowed to the owner
        if hasattr(obj, 'user'):
            return obj.user == request.user
            
        # If we can't determine the owner, deny permission
        return False

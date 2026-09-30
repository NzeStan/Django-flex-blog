from rest_framework.exceptions import APIException
from django.utils.translation import gettext_lazy as _


class FlexBlogError(Exception):
    """Base exception for all blog-related errors."""
    pass


class ModelNotRegisteredError(FlexBlogError):
    """Raised when a model is not registered in the registry."""
    pass


class ConfigurationError(FlexBlogError):
    """Raised when there's a configuration error."""
    pass


class ContentError(FlexBlogError):
    """Raised when there's an error with the content."""
    pass


class PublishingError(APIException):
    """Raised when there's an error publishing an article."""
    status_code = 400
    default_detail = _('Could not publish the article.')
    default_code = 'publishing_error'


class CommentingError(APIException):
    """Raised when there's an error creating a comment."""
    status_code = 400
    default_detail = _('Could not create the comment.')
    default_code = 'commenting_error'


class MediaError(APIException):
    """Raised when there's an error handling media."""
    status_code = 400
    default_detail = _('Could not process media.')
    default_code = 'media_error'
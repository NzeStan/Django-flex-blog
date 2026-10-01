"""
Who may do what.

Roles map onto Django's own permission system, so you manage them with
groups in the admin:

* **Reader**: anyone. Reads published content.
* **Author**: holds ``flex_blog.add_article``. Writes and edits own articles.
* **Publisher**: holds ``flex_blog.publish_article`` (only needed while
  ARTICLES["require_publish_permission"] is True).
* **Editor**: holds ``flex_blog.change_article``. Edits any article.
* **Moderator**: holds ``flex_blog.moderate_comment``.

Superusers hold every permission. Override authorship entirely with
FLEX_BLOG["CAN_AUTHOR"] = "myapp.rules.can_author".
"""

from rest_framework import permissions

from flex_blog.conf import blog_settings


def _authenticated(user):
    return bool(user and user.is_authenticated and user.is_active)


def can_author(user):
    if not _authenticated(user):
        return False
    custom = blog_settings.import_from(blog_settings.CAN_AUTHOR)
    if custom:
        return bool(custom(user))
    return user.has_perm("flex_blog.add_article")


def is_editor(user):
    return _authenticated(user) and user.has_perm("flex_blog.change_article")


def is_moderator(user):
    return _authenticated(user) and user.has_perm("flex_blog.moderate_comment")


def can_publish(user):
    if not blog_settings.ARTICLES["require_publish_permission"]:
        return can_author(user)
    return _authenticated(user) and user.has_perm("flex_blog.publish_article")


def owns_article(user, article):
    return _authenticated(user) and article.author_id is not None and article.author.user_id == user.pk


def can_edit_article(user, article):
    return is_editor(user) or (owns_article(user, article) and can_author(user))


def can_read_full_content(user, article):
    """Members-only gate. Plug a paywall in with FLEX_BLOG["CONTENT_ACCESS_CHECK"]."""
    if article.visibility != article.Visibility.MEMBERS:
        return True
    if can_edit_article(user, article):
        return True
    custom = blog_settings.import_from(blog_settings.CONTENT_ACCESS_CHECK)
    if custom:
        return bool(custom(user, article))
    return _authenticated(user)


class ArticlePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        if view.action == "create":
            return can_author(request.user)
        return _authenticated(request.user)

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if view.action == "destroy":
            return request.user.has_perm("flex_blog.delete_article") or (owns_article(request.user, obj) and can_author(request.user))
        return can_edit_article(request.user, obj)


class ModelPermissionOrReadOnly(permissions.BasePermission):
    """Reads are public; writes need the matching Django model permission."""

    perms = {"POST": "add", "PUT": "change", "PATCH": "change", "DELETE": "delete"}

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        model = view.get_queryset().model
        action = self.perms.get(request.method)
        return _authenticated(request.user) and bool(action) and request.user.has_perm(
            f"{model._meta.app_label}.{action}_{model._meta.model_name}"
        )


class CommentPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        if view.action in ("create", "article_comments"):
            return _authenticated(request.user) or blog_settings.COMMENTS["allow_anonymous"]
        if view.action in ("approve", "reject", "spam"):
            return is_moderator(request.user)
        return _authenticated(request.user)

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS or view.action in ("flag", "article_comments"):
            return True
        if is_moderator(request.user):
            return True
        return obj.user_id is not None and obj.user_id == request.user.pk


class MediaPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return can_author(request.user)

    def has_object_permission(self, request, view, obj):
        if request.user.has_perm("flex_blog.change_media"):
            return True
        return obj.uploaded_by_id == request.user.pk

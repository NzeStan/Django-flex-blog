"""
Business logic. Views, the admin, management commands and your own code all
go through these functions, so rules (permissions aside) live in one place.
"""

from flex_blog.services import articles, comments, engagement, maintenance, newsletter

__all__ = ["articles", "comments", "engagement", "maintenance", "newsletter"]

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FlexBlogConfig(AppConfig):
    name = "flex_blog"
    verbose_name = _("Blog")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from flex_blog import checks, receivers  # noqa: F401  (registers system checks)

        receivers.connect()

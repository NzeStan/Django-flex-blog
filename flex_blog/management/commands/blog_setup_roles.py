from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

ROLES = {
    "Blog authors": [
        "add_article", "view_article", "add_media", "view_media", "add_tag", "view_tag",
    ],
    "Blog editors": [
        "add_article", "change_article", "delete_article", "view_article", "publish_article",
        "add_category", "change_category", "delete_category", "view_category",
        "add_tag", "change_tag", "delete_tag", "view_tag",
        "add_series", "change_series", "delete_series", "view_series",
        "add_media", "change_media", "delete_media", "view_media",
        "add_author", "change_author", "view_author",
        "moderate_comment", "change_comment", "view_comment",
    ],
    "Blog moderators": ["moderate_comment", "change_comment", "view_comment", "view_article"],
}


class Command(BaseCommand):
    help = "Create (or update) the 'Blog authors', 'Blog editors' and 'Blog moderators' groups. Idempotent."

    def handle(self, *args, **options):
        for name, codenames in ROLES.items():
            group, _created = Group.objects.get_or_create(name=name)
            perms = Permission.objects.filter(content_type__app_label="flex_blog", codename__in=codenames)
            group.permissions.add(*perms)
            self.stdout.write(self.style.SUCCESS(f"{name}: {perms.count()} permissions"))
        self.stdout.write("Add users to these groups in the admin to give them blog roles.")

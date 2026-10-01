from django.core.management.base import BaseCommand

from flex_blog.services import maintenance


class Command(BaseCommand):
    help = (
        "Periodic housekeeping: announce scheduled articles whose time has come, retry failed "
        "webhooks, purge expired idempotency keys and stale data. Safe to run every minute from cron."
    )

    def handle(self, *args, **options):
        result = maintenance.run_all()
        for key, value in result.items():
            self.stdout.write(f"{key}: {value}")

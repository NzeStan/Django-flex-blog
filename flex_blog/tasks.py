"""
Background work, with or without Celery.

Every job here is a plain function taking JSON-serialisable arguments. When
Celery is installed each one is also registered as a Celery task named
``flex_blog.<function name>``. ``enqueue`` picks the runner configured in
FLEX_BLOG["TASKS"]["backend"]:

* ``"sync"`` (default): run in-process right after the transaction commits.
* ``"celery"``: send to your Celery workers after the transaction commits.

Periodic jobs (schedule them with Celery beat, or run
``manage.py blog_maintenance`` from cron)::

    CELERY_BEAT_SCHEDULE = {
        "flex-blog-maintenance": {"task": "flex_blog.run_maintenance", "schedule": 60.0},
    }

Every job is idempotent: running it twice, or retrying it after a crash,
never double-publishes, double-counts or double-sends.
"""

import logging

from django.db import transaction

from flex_blog.conf import blog_settings

logger = logging.getLogger("flex_blog")

try:  # pragma: no cover - exercised only when Celery is installed
    from celery import shared_task
except ImportError:  # pragma: no cover
    shared_task = None


def job(**celery_options):
    def decorator(func):
        if shared_task is not None:
            func.celery_task = shared_task(name=f"flex_blog.{func.__name__}", **celery_options)(func)
        return func

    return decorator


def enqueue(func, *args, **kwargs):
    """Run ``func(*args, **kwargs)`` in the background once the transaction commits."""
    backend = blog_settings.TASKS["backend"]

    def run():
        if backend == "celery":
            task = getattr(func, "celery_task", None)
            if task is None:
                raise RuntimeError("FLEX_BLOG TASKS backend is 'celery' but Celery is not installed.")
            options = {}
            if blog_settings.TASKS.get("queue"):
                options["queue"] = blog_settings.TASKS["queue"]
            task.apply_async(args=args, kwargs=kwargs, **options)
            return
        try:
            func(*args, **kwargs)
        except Exception:
            logger.exception("flex_blog: background job %s failed", func.__name__)

    transaction.on_commit(run)


# --- jobs ------------------------------------------------------------------


@job()
def announce_article(article_id):
    from flex_blog.services import articles

    articles.announce(article_id)


@job()
def increment_views(article_id, amount=1):
    from django.db.models import F

    from flex_blog.models import Article

    Article.objects.filter(pk=article_id).update(views_count=F("views_count") + amount)


@job()
def deliver_notification(message):
    from flex_blog.notifications import deliver

    deliver(message)


@job()
def send_newsletter_for_article(article_id):
    from flex_blog.services import newsletter

    newsletter.fan_out(article_id)


@job()
def send_newsletter_batch(article_id, subscriber_ids):
    from flex_blog.services import newsletter

    newsletter.send_batch(article_id, subscriber_ids)


@job()
def send_subscription_confirmation(subscriber_id):
    from flex_blog.services import newsletter

    newsletter.send_confirmation(subscriber_id)


@job(autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=3600, max_retries=5)
def deliver_webhook(delivery_id):
    from flex_blog import webhooks

    webhooks.deliver(delivery_id, raise_on_failure=blog_settings.TASKS["backend"] == "celery")


@job()
def run_maintenance():
    from flex_blog.services import maintenance

    return maintenance.run_all()

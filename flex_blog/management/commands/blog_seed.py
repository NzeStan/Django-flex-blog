from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from flex_blog.models import Article, Author, Category, Series
from flex_blog.services.articles import set_tags

SAMPLE = """## Why this matters

Writing is thinking made visible. This sample article shows **Markdown**,
lists, code and tables rendered and sanitised by flex_blog.

- Fast to set up
- Secure by default
- Extensible through signals

```python
print("Hello from flex_blog")
```

| Feature | Status |
|---------|--------|
| Comments | ✅ |
| Newsletter | ✅ |
"""


class Command(BaseCommand):
    help = "Create demo content (an author, categories, a series and articles) to try the API. Idempotent."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo-author")
        parser.add_argument("--articles", type=int, default=6)

    def handle(self, *args, username, articles, **options):
        User = get_user_model()
        user, created = User._default_manager.get_or_create(**{User.USERNAME_FIELD: username})
        if created:
            user.set_unusable_password()
            user.save()
        author = Author.for_user(user)
        if not author.bio:
            author.bio = "Demo author created by blog_seed."
            author.save()
        tech, _ = Category.objects.get_or_create(slug="technology", defaults={"name": "Technology"})
        Category.objects.get_or_create(slug="python", defaults={"name": "Python", "parent": tech})
        Category.objects.get_or_create(slug="culture", defaults={"name": "Culture"})
        series, _ = Series.objects.get_or_create(slug="getting-started", defaults={"title": "Getting started", "author": author})
        now = timezone.now()
        for index in range(1, articles + 1):
            slug = f"demo-article-{index}"
            if Article.objects.filter(slug=slug).exists():
                continue
            article = Article.objects.create(
                slug=slug, title=f"Demo article {index}", subtitle="Seeded by flex_blog", content=SAMPLE,
                author=author, status=Article.Status.PUBLISHED, published_at=now - timedelta(days=index),
                is_featured=index == 1, series=series if index <= 3 else None, series_order=index,
                announced_at=now,  # demo data never emails subscribers
            )
            article.categories.set([tech] if index % 2 else [Category.objects.get(slug="culture")])
            set_tags(article, ["demo", "django", "nigeria" if index % 2 else "africa"])
        self.stdout.write(self.style.SUCCESS(f"Demo content ready ({Article.objects.count()} articles in total)."))

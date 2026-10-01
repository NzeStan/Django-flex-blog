# django-flex-blog

**A complete, secure, headless blog backend for Django.** Install it, add four lines of configuration, and your frontend (React, Next.js, Vue, Flutter, a mobile app...) has a production-grade blog API: articles, authors, categories, tags, series, threaded comments with moderation, reactions, bookmarks, a double opt-in newsletter, in-app and email notifications, signed webhooks, search, RSS/Atom feeds, sitemaps and an editorial workflow.

Every feature can be turned off. Built-in behaviour hangs off documented signals, so you can extend or replace any of it without forking.

- Backend only: a JSON REST API built on Django REST Framework, plus the Django admin. No templates or CSS to fight with.
- Secure by default. All HTML is sanitized, uploads are verified, every write is throttled, permissions are role based, and private data is never exposed.
- Built for traffic. Counters are atomic, anonymous responses are cached and invalidated by generation, indexed queries avoid N+1, and Celery is optional.
- Idempotent. `Idempotency-Key` headers are supported, publishing and newsletters happen exactly once, and repeated PUT/DELETE calls are harmless.
- Works on Django 4.2 to 6.x and Python 3.10 to 3.14, with SQLite or PostgreSQL.

---

## Contents

1. [Quick start (10 minutes)](#quick-start)
2. [What you get: API reference](#api-reference)
3. [Roles and permissions](#roles-and-permissions)
4. [Configuration](#configuration)
5. [Events, plugins and notifications](#events-plugins-and-notifications)
6. [Background tasks and Celery](#background-tasks-and-celery)
7. [Idempotency and concurrency](#idempotency-and-concurrency)
8. [Security](#security)
9. [Going to production](#going-to-production)
10. [Customising](#customising)
11. [Management commands](#management-commands)

---

## Quick start

```bash
pip install django-flex-blog
# optional extras: django-flex-blog[celery]  django-flex-blog[postgres]
```

**1. Settings**

```python
INSTALLED_APPS = [
    # ...django.contrib apps...
    "rest_framework",
    "django_filters",
    "flex_blog",
]

FLEX_BLOG = {
    "SITE_URL": "https://example.com",   # your public site, used in emails and feeds
    "SITE_NAME": "My Blog",
}

MEDIA_ROOT = BASE_DIR / "media"          # where uploads go (or configure STORAGES for S3 etc.)
MEDIA_URL = "/media/"
```

**2. URLs**

```python
from django.urls import include, path

urlpatterns = [
    # ...
    path("api/blog/", include("flex_blog.urls")),
]
```

**3. Database and roles**

```bash
python manage.py migrate
python manage.py blog_setup_roles     # creates "Blog authors", "Blog editors", "Blog moderators" groups
python manage.py blog_seed            # optional demo content
```

**4. Done.** Open `/api/blog/` for the browsable API, and use `/admin/` to write.

```bash
curl https://example.com/api/blog/articles/
```

Superusers can do everything. To give other people access, add them to one of the groups in the admin.

---

## API reference

All paths below are relative to where you mounted `flex_blog.urls`. Lists are paginated (`?page=`, `?page_size=` up to 100) and return `{count, next, previous, results}`.

### Articles

| Method & path | Who | What |
|---|---|---|
| `GET /articles/` | anyone | Public feed. Pinned articles come first. |
| `GET /articles/?q=jollof rice` | anyone | Search, ranked by relevance |
| `GET /articles/?category=tech&tag=django,python&author=ada&series=course&language=yo&is_featured=true&year=2026&month=3&published_after=…&ordering=-views_count` | anyone | Filters (combine freely). `category` includes sub-categories. |
| `GET /articles/?scope=mine` | authors | Your own articles in any status |
| `GET /articles/?scope=all&status=review` | editors | All articles, e.g. the review queue |
| `GET /articles/{slug}/` | anyone | Detail: `content_html` (sanitized), `table_of_contents`, `reactions`, `viewer` state, `series_navigation`. Old slugs return **301** to the new one. |
| `GET /articles/{slug}/?preview={token}` | link holders | View an unpublished article |
| `POST /articles/` | authors | Create (JSON or multipart with `cover_image`). Tags are names and are created on the fly; categories and series are slugs. |
| `PATCH /articles/{slug}/` | owner, editors | Update. Send `version` to get a **409** instead of overwriting a concurrent edit. |
| `DELETE /articles/{slug}/` | owner, editors | Delete |
| `POST /articles/{slug}/publish/` | publishers | Publish now, or `{"published_at": "<future>"}` to schedule. Idempotent. |
| `POST /articles/{slug}/unpublish/` | publishers | Back to draft, or `{"status": "archived"}` |
| `POST /articles/{slug}/submit/` | authors | Send to editorial review |
| `POST /articles/{slug}/preview-link/` | owner, editors | Returns `{token, url, expires_in}` |
| `GET /articles/{slug}/revisions/` | owner, editors | Edit history |
| `POST /articles/{slug}/revisions/{id}/restore/` | owner, editors | Roll back |
| `GET /articles/{slug}/related/` | anyone | Articles sharing tags/categories |
| `GET /articles/popular/?days=30` | anyone | Most viewed recently |
| `GET /articles/archive/` | anyone | `[{year, month, count}]` |
| `PUT` / `DELETE /articles/{slug}/reactions/{kind}/` | signed in | React / un-react (idempotent) |
| `PUT` / `DELETE /articles/{slug}/bookmark/` | signed in | Save for later (idempotent) |
| `GET` / `POST /articles/{slug}/comments/` | anyone / commenters | Comments of an article (flat list with `parent` and `depth`; `?parent=none` for top level) |

Article writes accept: `title, subtitle, slug, summary, content, content_format (markdown|html|plain), categories, tags, series, series_order, cover_image, cover_image_alt, status, visibility (public|unlisted|members), published_at, allow_comments, language, meta_title, meta_description, canonical_url, noindex, extra_data, version`. Editors can also set `is_featured`, `is_pinned` and `author`.

### Comments

| Method & path | Who | What |
|---|---|---|
| `GET /comments/?article={slug}&parent={id\|none}&status=pending` | anyone (moderators see all statuses) | Site-wide list |
| `POST /comments/` | commenters | `{article, content, parent?}` (guests also send `author_name`, `author_email`) |
| `PATCH /comments/{id}/` | author (within the edit window), moderators | Edit `content` |
| `DELETE /comments/{id}/` | author, moderators | Soft delete; replies keep their thread |
| `POST /comments/{id}/approve/` `…/reject/` `…/spam/` | moderators | Moderate (idempotent) |
| `POST /comments/{id}/flag/` | signed in | Report; enough flags send it back to moderation |

### Everything else

| Path | What |
|---|---|
| `GET /authors/`, `GET /authors/{slug}/` | Public profiles with article counts |
| `GET` / `PATCH /authors/me/` | The signed-in author's own profile |
| `/categories/`, `/categories/tree/`, `/tags/`, `/series/` | Taxonomy (writes need the matching model permission) |
| `GET /search/?q=` | One-box search: top articles, categories, tags, authors |
| `/media/` | Media library for authors (multipart `file` upload) |
| `GET /bookmarks/` | The reader's saved articles |
| `GET /notifications/`, `GET …/unread-count/`, `POST …/{id}/read/`, `POST …/read-all/` | In-app inbox |
| `POST /newsletter/subscribe/`, `…/confirm/`, `…/unsubscribe/` | Double opt-in newsletter (`{email}` / `{token}`) |
| `GET /stats/` | Dashboard numbers (editors) |
| `GET /feeds/rss/`, `/feeds/atom/`, `/feeds/category/{slug}/`, `/feeds/tag/{slug}/`, `/feeds/author/{slug}/` | Feeds |
| `GET /sitemap.xml` | Sitemap of the frontend URLs |

### Frontend URLs

The API is headless, so tell it where readers see things. These values are used in feeds, sitemaps, emails and webhooks:

```python
FLEX_BLOG = {
    "SITE_URL": "https://example.com",
    "FRONTEND_URLS": {
        "article": "/blog/{slug}/",
        "newsletter_confirm": "/newsletter/confirm/?token={token}",
        "newsletter_unsubscribe": "/newsletter/unsubscribe/?token={token}",
        "article_preview": "/blog/preview/{slug}/?token={token}",
        # also: category, tag, author, series
    },
}
```

Your newsletter confirmation page reads `token` from its own URL and `POST`s it to `/newsletter/confirm/`.

---

## Roles and permissions

Roles are plain Django permissions, so you manage them with groups in the admin (`blog_setup_roles` creates sensible groups):

| Role | Permission | Can |
|---|---|---|
| Reader | none | Read, comment (if allowed), react, bookmark |
| Author | `flex_blog.add_article` | Write and edit **own** articles, upload media, manage own profile |
| Publisher | `flex_blog.publish_article` | Publish / schedule / unpublish |
| Editor | `flex_blog.change_article` | Edit any article, feature/pin, set the author |
| Moderator | `flex_blog.moderate_comment` | Approve/reject comments, see commenter emails |

- **One-person blog?** Set `"ARTICLES": {"require_publish_permission": False}` so every author can publish.
- **Your own rules?** Use `"CAN_AUTHOR": "myapp.rules.can_author"` (a function `(user) -> bool`).
- **Paywall or members area?** Articles with `visibility="members"` show their teaser to everyone but full content only to signed-in users. To plug in your subscription check, use `"CONTENT_ACCESS_CHECK": "myapp.billing.can_read"` (a function `(user, article) -> bool`).

---

## Configuration

Everything lives in one dict. Anything you don't set falls back to the defaults, and nested dicts are merged, so you only override the keys you need. Below are the defaults:

```python
FLEX_BLOG = {
    "FEATURES": {            # set any to False to remove it completely
        "comments": True, "reactions": True, "bookmarks": True, "series": True, "media": True,
        "newsletter": True, "notifications": True, "webhooks": True, "search": True,
        "feeds": True, "sitemaps": True, "revisions": True, "view_counting": True,
        "idempotency": True, "response_cache": True, "preview_links": True,
        "slug_redirects": True, "admin": True,
    },
    "ARTICLES": {
        "content_formats": ["markdown", "html", "plain"], "default_content_format": "markdown",
        "words_per_minute": 200, "excerpt_length": 300, "max_tags": 10, "max_categories": 5,
        "require_publish_permission": True, "auto_create_author_profile": True,
        "slug_allow_unicode": False, "related_count": 5, "preview_link_max_age": 259200,
    },
    "COMMENTS": {
        "allow_anonymous": False,
        "moderation": "first_time",      # none | anonymous | first_time | all
        "max_depth": 4, "min_length": 2, "max_length": 5000, "max_links": 3,
        "blocked_words": [], "edit_window_minutes": 15, "close_after_days": None,
        "store_ip_address": False, "honeypot_field": "website_hp", "flag_threshold": 5,
        "spam_checker": None,            # "myapp.spam.check" -> (comment, request) -> bool
        "markdown": True,
    },
    "REACTIONS": {"kinds": ["like"]},    # e.g. ["like", "love", "clap", "fire"]
    "VIEW_COUNTING": {"dedupe_seconds": 1800, "async": False},
    "NEWSLETTER": {"double_opt_in": True, "confirm_max_age": 259200, "send_on_publish": True,
                   "batch_size": 200, "from_email": None},
    "NOTIFICATIONS": {
        "backends": ["flex_blog.notifications.backends.InAppBackend",
                     "flex_blog.notifications.backends.EmailBackend"],
        "events": {"comment_on_article": True, "comment_reply": True,
                   "comment_approved": True, "comment_pending": True},
        "moderator_emails": [], "recipient_filter": None, "from_email": None,
    },
    "WEBHOOKS": {"timeout": 5, "max_retries": 5, "allow_http": False, "allow_private_hosts": False},
    "TASKS": {"backend": "sync", "queue": None},          # or "celery"
    "CACHE": {"alias": "default", "timeout": 300, "key_prefix": "flexblog"},
    "THROTTLE_RATES": {"comments": "10/min", "reactions": "60/min", "newsletter": "5/hour",
                       "search": "60/min", "uploads": "30/hour", "write": "120/min"},
    "PAGINATION": {"page_size": 20, "max_page_size": 100},
    "MEDIA": {"storage": None, "upload_to": "flex_blog/%Y/%m/", "max_upload_size": 10485760,
              "allowed_extensions": ["jpg", "jpeg", "png", "gif", "webp", "avif", "pdf", "mp4", "mp3"],
              "max_image_pixels": 50000000},
    "IDEMPOTENCY": {"header": "Idempotency-Key", "ttl_seconds": 86400},
    "SEARCH": {"backend": "flex_blog.search.DatabaseSearchBackend", "config": "english"},
    "FEEDS": {"items": 20, "description": ""},
    "SANITIZER": {...},                  # allow-listed tags/attributes/URL schemes
    "SERIALIZERS": {},                   # swap any serializer, see "Customising"
    "CONTENT_ACCESS_CHECK": None,
    "CAN_AUTHOR": None,
}
```

`python manage.py check` validates your settings (typos, missing apps, imports that can't be resolved), and `check --deploy` warns about production pitfalls.

---

## Events, plugins and notifications

**Domain events are the plugin system.** Everything the package does after a state change (notifications, newsletters, webhooks, cache invalidation) is an ordinary receiver of these signals. Your code is a first-class citizen right next to it.

```python
from django.dispatch import receiver
from flex_blog.signals import article_published, comment_posted

@receiver(article_published)
def share_on_socials(sender, article, event_id, **kwargs):
    ...  # event_id is unique per event: use it as your own idempotency key

@receiver(comment_posted)
def index_for_moderation_ai(sender, comment, **kwargs):
    ...
```

| Event | Arguments |
|---|---|
| `article_published` | `article` (fires once per article, ever, even when scheduled) |
| `article_unpublished` | `article` |
| `article_viewed` | `article`, `user` (after view de-duplication) |
| `comment_posted` | `comment` (any status) |
| `comment_approved` | `comment`, `moderator` (None when auto-approved) |
| `comment_rejected` | `comment`, `moderator`, `status` |
| `reaction_added` / `reaction_removed` | `reaction` / `article, user, kind` |
| `bookmark_added` | `bookmark` |
| `subscriber_confirmed` / `subscriber_unsubscribed` | `subscriber` |

Events are sent **after the database transaction commits** (so receivers never see rolled-back data), and a failing receiver is logged but never breaks the request or the other receivers.

### How notifications are wired (and why)

```
event ──► receiver decides who should hear about it ──► NotificationMessage
      ──► queued after commit (sync or Celery) ──► every channel backend .send()
```

- **Who gets notified** is decided by receivers: the article author on a new comment, the parent commenter on a reply, the commenter when their comment is approved, and `moderator_emails` when something waits for moderation. Toggle each under `NOTIFICATIONS["events"]`, or filter per user with `recipient_filter` (a hook for "user preferences").
- **How they're delivered** is decided by channel backends. In-app (`/notifications/` inbox) and email ship built in, and adding SMS, WhatsApp, push or Slack takes about ten lines:

```python
from flex_blog.notifications.backends import BaseBackend

class SMSBackend(BaseBackend):
    name = "sms"
    def send(self, message):          # message.title, .body, .url, .event, .get_recipient()
        user = message.get_recipient()
        termii.send(user.profile.phone, message.title)

FLEX_BLOG = {"NOTIFICATIONS": {"backends": [
    "flex_blog.notifications.backends.InAppBackend",
    "myapp.notify.SMSBackend",
]}}
```

- **Exactly once per channel.** Each message carries a `dedupe_key`. Delivery claims it in the database first, so a retried task never sends twice. If sending fails, the claim is released so a retry can succeed.
- **Your own notifications** can use the same pipeline: `from flex_blog.notifications import notify, NotificationMessage`.
- **Email text** comes from overridable templates in `flex_blog/email/*.txt`.

### Webhooks (no code)

In the admin, add a **Webhook endpoint** with a URL and the events you want (or `["*"]`). Each event is POSTed as JSON, and every request is signed:

```
X-FlexBlog-Event: article_published
X-FlexBlog-Delivery: <event id, the same on every retry>
X-FlexBlog-Signature: t=<timestamp>,v1=<HMAC-SHA256(secret, "<t>.<body>")>
```

Verify the signature with `flex_blog.webhooks.verify_signature(secret, body, header)`.

- Failed deliveries retry with exponential backoff, and every attempt is logged in the admin.
- URLs must be `https` and may not point to private or internal addresses (SSRF protection), and redirects are not followed.

---

## Background tasks and Celery

Background work (newsletters, notifications, webhooks, view counters) goes through `flex_blog.tasks.enqueue` and always runs **after the transaction commits**:

- `"sync"` (default): runs in the same process. Nothing extra to install, which is perfect to start with.
- `"celery"`: sends the work to your Celery workers. Recommended once your newsletter has thousands of subscribers.

```python
# pip install django-flex-blog[celery]
FLEX_BLOG = {"TASKS": {"backend": "celery", "queue": "blog"}}

CELERY_BEAT_SCHEDULE = {
    "flex-blog-maintenance": {"task": "flex_blog.run_maintenance", "schedule": 60.0},
}
```

No Celery? Run `python manage.py blog_maintenance` every minute from cron. It publishes scheduled articles, retries failed webhooks and cleans up expired data. Even without it, scheduled articles become visible at the right time, because visibility is computed from `published_at`. Maintenance only fires the "published" event (emails, webhooks) for them.

---

## Idempotency and concurrency

- **`Idempotency-Key` header** on any POST/PUT/PATCH/DELETE: the first request runs, retries with the same key get the stored response back (`Idempotent-Replayed: true`) without running anything again, a retry while the original is still running gets 409, and reusing a key with a different body gets 422. Keys are scoped per user (per IP hash for guests) and expire after `ttl_seconds`. This is safe across many servers because it is enforced by a unique database constraint.
- **Idempotent by design**: publish, unpublish, approve, reactions, bookmarks, subscribe, confirm and unsubscribe can all be repeated safely.
- **Exactly-once side effects**: `article_published` is guarded by a conditional UPDATE, and newsletter emails, notifications and webhooks are guarded by unique delivery receipts.
- **No lost updates**: article edits accept `version`. A stale edit gets **409 Conflict**, and the row is locked while it is checked.
- **Atomic counters**: views, comments and reactions use `UPDATE … SET n = n + 1`, never read-modify-write. Run `blog_recount` to rebuild them from scratch at any time.
- **Race-safe slugs and tags**: losing a unique-constraint race retries instead of failing.

---

## Security

- **XSS:** all HTML (Markdown, HTML and comments) is sanitized once, on save, with [nh3](https://github.com/messense/nh3) using a strict allow-list. Links get `rel="noopener noreferrer nofollow"`, `javascript:` URLs are removed, and comments get an even tighter allow-list.
- **Uploads:** size limit, extension allow-list, and a check with Pillow that the file really is the image it claims to be. This blocks polyglots, HTML/SVG renamed to `.png`, and decompression bombs. Files get random names.
- **Abuse:** per-action throttles (comments, reactions, newsletter, search, uploads, writes), a comment honeypot, link and length limits, blocked words, a pluggable spam checker (Akismet etc.), and flagging.
- **Privacy:** commenter emails and IPs are only shown to moderators, storing IPs is off by default, newsletter answers never reveal whether an address is subscribed, and drafts are never counted in public counters.
- **Access:** UUID primary keys, explicit serializer allow-lists (no mass assignment), drafts return 404 to non-owners, and the revision history is visible to editors only.
- **Webhooks:** HMAC-signed, https only, SSRF guarded, no redirects.

---

## Going to production

1. Use **Redis or Memcached** as the cache. Throttling, view de-duplication and response caching need a cache that all workers share (`check --deploy` warns otherwise).
2. Behind a load balancer, set `REST_FRAMEWORK["NUM_PROXIES"]` so client IPs (throttles) can't be spoofed.
3. Set `SITE_URL`, a real `EMAIL_BACKEND`/`MAILERS`, and `DEFAULT_FROM_EMAIL`.
4. Use `TASKS = {"backend": "celery"}` for large newsletters, and schedule `flex_blog.run_maintenance`.
5. PostgreSQL? Switch to ranked full-text search: `"SEARCH": {"backend": "flex_blog.search.PostgresSearchBackend"}`.
6. Store media on S3/GCS: define a storage in Django's `STORAGES` and set `"MEDIA": {"storage": "<alias>"}`.

---

## Customising

- **Serializers:** swap any of them by name: `"SERIALIZERS": {"article_detail": "myapp.api.ArticleDetail"}`. The names are `article_list`, `article_detail`, `article_write`, `comment`, `comment_create`, `author`, `author_profile`, `category`, `tag`, `series` and `media`. Subclass ours to add fields.
- **Extra data without migrations:** articles, authors, categories, series, media and comments have an `extra_data` JSON field. Article `extra_data` is public, so don't put secrets in it.
- **Views:** every viewset is importable from `flex_blog.views`. Subclass one and register your own router if you need to.
- **Search:** subclass `flex_blog.search.BaseSearchBackend` (e.g. for Meilisearch or Elasticsearch) and keep your index fresh with the signals.
- **Admin:** set `FEATURES["admin"] = False` and register your own, or reuse `flex_blog.admin.ArticleAdmin`.
- **Business logic:** use the same functions the API uses: `flex_blog.services.articles.publish(article)`, `services.comments.moderate(...)`, `services.engagement.add_reaction(...)` and so on.
- **Translations:** every string is translatable, and articles have a `language` field validated against `settings.LANGUAGES`.

---

## Management commands

| Command | What |
|---|---|
| `blog_setup_roles` | Create the author/editor/moderator groups (idempotent) |
| `blog_seed` | Demo content to play with (idempotent) |
| `blog_maintenance` | Announce scheduled articles, retry webhooks, purge expired data. Run every minute. |
| `blog_recount` | Rebuild comment/reaction counters |
| `blog_export [-o file.json] [--no-comments]` | Export everything as portable JSON |
| `blog_import file.json` | Import (idempotent: re-running updates rather than duplicates, and never emails subscribers) |
| `blog_cleanup [--spam-days 30] [--drafts-days N] [--dry-run]` | Delete old spam; drafts only if you ask |

---

## Development

```bash
pip install -e ".[test,celery]"
pytest                               # SQLite
FLEX_BLOG_TEST_DB=postgres pytest    # adds real parallel-write tests on PostgreSQL
```

MIT licensed. Contributions welcome!

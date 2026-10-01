# Changelog

## 1.0.0 (2026-10-01)

First public release: a complete rewrite of the 0.1 prototype.

### Added
- Articles with Markdown/HTML/plain content, sanitised rendering, table of contents, reading time,
  scheduling, visibility (public / unlisted / members), SEO fields, revisions, slug redirects,
  preview links and optimistic locking.
- Authors, hierarchical categories, tags (created by name), series with navigation.
- Threaded comments with moderation modes, spam hooks, honeypot, flagging, edit window and soft delete.
- Reactions, bookmarks, view counting with de-duplication.
- Double opt-in newsletter with batched, exactly-once delivery.
- Domain event signals; in-app and email notifications with pluggable channel backends; signed webhooks with retries.
- Idempotency-Key support, per-action throttling, anonymous response caching.
- Optional Celery backend; `blog_maintenance`, `blog_recount`, `blog_export`, `blog_import`,
  `blog_seed`, `blog_setup_roles`, `blog_cleanup` commands.
- RSS/Atom feeds, sitemap, search (database or PostgreSQL full-text), system checks.

### Changed (from 0.1)
- UUID primary keys always (`USE_UUID` and swappable `BLOG_MODELS` removed: they cannot work with
  shipped migrations). Extend models through `extra_data`, services, signals and serializer overrides.
- Dropped `django-mptt`, `django-taggit` and `python-slugify` dependencies.
- `cleanup_blog`/`export_blog`/`import_blog` replaced by `blog_*` commands; cleanup never deletes
  drafts unless asked.

"""
Content rendering: Markdown/HTML/plain text in, sanitized HTML out.

Rendering happens once on save, never per request. All output goes through
``nh3`` (a Rust HTML sanitizer) with the allow-list from FLEX_BLOG["SANITIZER"],
so stored HTML is always safe to inject into a page.
"""

import html
import math
import re
from dataclasses import dataclass, field

import nh3
from django.utils.text import slugify

from flex_blog.conf import blog_settings

_TAG_RE = re.compile(r"<[^>]+>")
_HEADING_RE = re.compile(r"<h([2-4])>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
_WS_RE = re.compile(r"\s+")
_LINK_RE = re.compile(r"https?://|www\.", re.IGNORECASE)


@dataclass
class RenderedContent:
    html: str
    text: str
    toc: list = field(default_factory=list)
    word_count: int = 0
    reading_time: int = 0


def _markdown_to_html(source, allow_html=False):
    from markdown_it import MarkdownIt

    # Raw HTML inside Markdown is allowed for articles (it is sanitised right
    # after); for comments it is rendered as text.
    md = MarkdownIt("commonmark", {"html": allow_html, "linkify": False, "typographer": False})
    md.enable(["table", "strikethrough"])
    return md.render(source)


def sanitize_html(value, *, tags=None, attributes=None):
    conf = blog_settings.SANITIZER
    # nh3 sets rel itself, so "rel" must not appear in the attribute allow-list.
    allowed_attrs = {k: set(v) - {"rel"} for k, v in (attributes or conf["attributes"]).items()}
    return nh3.clean(
        value or "",
        tags=set(tags if tags is not None else conf["tags"]),
        attributes=allowed_attrs,
        url_schemes=set(conf["url_schemes"]),
        link_rel="noopener noreferrer nofollow",
        strip_comments=True,
    )


def html_to_text(value):
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", value or ""))).strip()


def _add_heading_ids(rendered):
    """Give h2-h4 stable ids and return (html, table_of_contents)."""
    toc, used = [], set()

    def replace(match):
        level, inner = match.group(1), match.group(2)
        text = html_to_text(inner)
        base = slugify(text, allow_unicode=True) or "section"
        anchor, n = base, 2
        while anchor in used:
            anchor, n = f"{base}-{n}", n + 1
        used.add(anchor)
        toc.append({"id": anchor, "text": text, "level": int(level)})
        return f'<h{level} id="{anchor}">{inner}</h{level}>'

    return _HEADING_RE.sub(replace, rendered), toc


def render_content(source, content_format="markdown"):
    source = source or ""
    if content_format == "markdown":
        raw = _markdown_to_html(source, allow_html=True)
    elif content_format == "html":
        raw = source
    else:
        raw = "".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in re.split(r"\n\s*\n", source.strip()) if p)
    cleaned = sanitize_html(raw)
    cleaned, toc = _add_heading_ids(cleaned)
    text = html_to_text(cleaned)
    words = len(text.split())
    wpm = max(int(blog_settings.ARTICLES["words_per_minute"]), 1)
    return RenderedContent(
        html=cleaned,
        text=text,
        toc=toc,
        word_count=words,
        reading_time=max(1, math.ceil(words / wpm)) if words else 0,
    )


def render_comment(source):
    """Comments: optional Markdown, tighter tag allow-list, no headings/images."""
    conf = blog_settings.SANITIZER
    if blog_settings.COMMENTS["markdown"]:
        raw = _markdown_to_html(source or "")
    else:
        raw = "".join(f"<p>{html.escape(p)}</p>" for p in re.split(r"\n\s*\n", (source or "").strip()) if p)
    return sanitize_html(raw, tags=conf["comment_tags"], attributes={"a": ["href"]})


def make_excerpt(text, length=None):
    length = length or blog_settings.ARTICLES["excerpt_length"]
    text = (text or "").strip()
    if len(text) <= length:
        return text
    cut = text[:length].rsplit(" ", 1)[0].rstrip(",.;:-")
    return f"{cut}…"


def count_links(text):
    return len(_LINK_RE.findall(text or ""))

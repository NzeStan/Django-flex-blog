from urllib.parse import quote

from flex_blog.conf import blog_settings


def frontend_url(name, absolute=False, **params):
    """
    Build the public (frontend) URL for a named page from FRONTEND_URLS.

    Parameters are URL-quoted. With ``absolute=True`` the configured SITE_URL
    is prepended unless the template is already absolute.
    """
    template = blog_settings.FRONTEND_URLS.get(name)
    if not template:
        return ""
    path = template.format(**{k: quote(str(v), safe="") for k, v in params.items()})
    if absolute:
        return absolute_url(path)
    return path


def absolute_url(path):
    if path.startswith(("http://", "https://")):
        return path
    return blog_settings.SITE_URL.rstrip("/") + path

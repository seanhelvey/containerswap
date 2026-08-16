import hashlib
from functools import cache

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app import storage
from app.config import BASE_DIR, settings
from app.i18n import DEFAULT_LANG, negotiate, translate

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

CATEGORIES = ["deli", "yogurt", "jars", "other"]


def _lang(request: Request) -> str:
    return getattr(request.state, "lang", DEFAULT_LANG)


@cache
def _asset_version(path: str) -> str:
    digest = hashlib.sha256((BASE_DIR / "static" / path).read_bytes()).hexdigest()
    return digest[:10]


def static_url(path: str) -> str:
    """`/static/<path>?v=<content hash>`.

    Cloudflare sits in front of this app and caches static files by URL for hours.
    Without a version in the URL, a CSS/JS edit ships in the HTML immediately but
    the file it references keeps serving the pre-edit version from cache until the
    entry expires — a real outage once (the signup honeypot field rendered visible
    for everyone hitting a cached edge). A content hash makes an edited file a new
    URL, which is a guaranteed cache miss, with no manual purge required.
    """
    return f"/static/{path}?v={_asset_version(path)}"


def render(request: Request, template: str, context: dict | None = None, **kwargs):
    """Render with the globals every page needs: translation, session user, CSRF."""
    from app.auth import read_session

    session = read_session(request)
    lang = _lang(request)
    base = {
        "request": request,
        "lang": lang,
        "t": lambda key, **params: translate(key, lang, **params),
        "settings": settings,
        "categories": CATEGORIES,
        # Templates must not build upload URLs themselves: the path differs between
        # local disk and the object store, and hardcoding /uploads/ silently 404s in
        # production.
        "image_url": storage.url_for,
        "static_url": static_url,
        "current_user": getattr(request.state, "user", None),
        "csrf_token": (session or {}).get("csrf", ""),
    }
    base.update(context or {})
    return templates.TemplateResponse(request=request, name=template, context=base, **kwargs)


def set_request_language(request: Request) -> None:
    request.state.lang = negotiate(request.headers.get("accept-language"))

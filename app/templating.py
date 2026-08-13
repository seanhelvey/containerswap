from fastapi import Request
from fastapi.templating import Jinja2Templates

from app import storage
from app.config import BASE_DIR, settings
from app.i18n import DEFAULT_LANG, negotiate, translate

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

CATEGORIES = ["jars", "deli", "yogurt", "other"]


def _lang(request: Request) -> str:
    return getattr(request.state, "lang", DEFAULT_LANG)


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
        "current_user": getattr(request.state, "user", None),
        "csrf_token": (session or {}).get("csrf", ""),
    }
    base.update(context or {})
    return templates.TemplateResponse(request=request, name=template, context=base, **kwargs)


def set_request_language(request: Request) -> None:
    request.state.lang = negotiate(request.headers.get("accept-language"))

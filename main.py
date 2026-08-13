import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.auth import get_current_user
from app.config import BASE_DIR, settings
from app.db import SessionLocal
from app.routes import account, listings
from app.templating import render, set_request_language

logger = logging.getLogger("containerswap")


def _img_src() -> str:
    """CSP sources for images.

    Listing photos are served from the object store's own domain in production, so
    that origin has to be listed or every photo is silently blocked by the browser.
    Locally they come from /uploads on this origin and 'self' already covers it.
    """
    sources = ["'self'", "data:", "blob:", "https://*.tile.openstreetmap.org"]
    if settings.uses_object_storage:
        sources.append(settings.supabase_url.rstrip("/"))
    return " ".join(sources)


_IMG_SRC = _img_src()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # No schema work here on purpose. Zero-downtime deploys start several instances
    # at once, so any create/alter on startup is a race between them. Schema changes
    # are applied by `alembic upgrade head`, run once before the deploy.
    if settings.secret_is_default and not settings.debug:
        # Loud, because a default signing key means forgeable sessions.
        logger.error(
            "CS_SECRET_KEY is unset in production. Sessions are forgeable. "
            "Set it in the FastAPI Cloud dashboard now."
        )
    yield


app = FastAPI(
    title=settings.site_name,
    description="Peer-to-peer swapping of used containers, so they get another life.",
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.debug else None,
    lifespan=lifespan,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach the negotiated language and the session user to every request, and set
    the security headers on every response."""
    set_request_language(request)

    db = SessionLocal()
    try:
        request.state.user = get_current_user(request, db)
    finally:
        db.close()

    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(self), camera=(self), microphone=()"
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        f"img-src {_IMG_SRC}; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "form-action 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "object-src 'none'",
    )
    if not settings.debug:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Send humans to a page and API clients to JSON."""
    accept = request.headers.get("accept", "")
    wants_json = request.url.path.startswith("/api") or (
        "application/json" in accept and "text/html" not in accept
    )
    wants_html = not wants_json

    if exc.status_code == 401 and wants_html:
        return RedirectResponse(f"/login?next={request.url.path}", status_code=303)
    if not wants_html:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    return render(
        request,
        "error.html",
        {"status_code": exc.status_code, "detail": exc.detail},
        status_code=exc.status_code,
    )


app.include_router(account.router)
app.include_router(listings.router)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Local dev only. In production uploads go to the object store and are served from
# its own domain, so there is nothing on local disk to mount — and mounting it would
# be a lie, since the filesystem does not survive a redeploy.
if not settings.uses_object_storage:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(settings.upload_dir)), name="uploads")


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(
        BASE_DIR / "static" / "manifest.webmanifest",
        media_type="application/manifest+json",
    )


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    """Served from the root so its scope covers the whole site."""
    return FileResponse(
        BASE_DIR / "static" / "js" / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/offline", include_in_schema=False)
def offline(request: Request):
    return render(request, "offline.html")


@app.get("/robots.txt", include_in_schema=False)
def robots():
    return Response("User-agent: *\nAllow: /\nDisallow: /inbox\n", media_type="text/plain")


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}

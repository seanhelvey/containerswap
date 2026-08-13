from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ratelimit
from app.auth import (
    clear_session_cookie,
    generate_display_name,
    hash_password,
    issue_session,
    normalize_display_name,
    normalize_email,
    require_user,
    set_session_cookie,
    validate_credentials,
    verify_csrf,
    verify_password,
)
from app.db import get_db
from app.models import User
from app.templating import render

router = APIRouter()


@router.get("/signup")
def signup_form(request: Request):
    if getattr(request.state, "user", None):
        return RedirectResponse("/", status_code=303)
    return render(request, "signup.html")


@router.post("/signup", dependencies=[Depends(ratelimit.limiter("signup"))])
def signup(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    display_name: str = Form(""),
    db: Session = Depends(get_db),
):
    address = normalize_email(email)
    chosen = normalize_display_name(display_name)
    error = validate_credentials(address, password, chosen)
    if error is None:
        exists = db.execute(select(User).where(User.email == address)).scalar_one_or_none()
        if exists:
            error = "auth.error.email_taken"

    if error:
        # Echo both back so a typo does not cost them the whole form.
        return render(
            request,
            "signup.html",
            {"error_key": error, "email": address, "display_name": chosen},
            status_code=400,
        )

    if not chosen:
        taken = set(db.execute(select(User.display_name)).scalars().all())
        chosen = generate_display_name(taken)

    user = User(email=address, display_name=chosen, password_hash=hash_password(password))
    db.add(user)
    db.commit()

    cookie, _ = issue_session(user.id)
    response = RedirectResponse("/", status_code=303)
    set_session_cookie(response, cookie)
    return response


@router.get("/login")
def login_form(request: Request, next: str = "/"):
    if getattr(request.state, "user", None):
        return RedirectResponse("/", status_code=303)
    return render(request, "login.html", {"next": _safe_next(next)})


@router.post("/login", dependencies=[Depends(ratelimit.limiter("login"))])
def login(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    address = normalize_email(email)
    user = db.execute(select(User).where(User.email == address)).scalar_one_or_none()

    # Same generic message either way: never reveal whether an account exists.
    if not user or not user.is_active or not verify_password(user.password_hash, password):
        return render(
            request,
            "login.html",
            {"error_key": "auth.error.invalid", "email": address, "next": _safe_next(next)},
            status_code=401,
        )

    cookie, _ = issue_session(user.id)
    response = RedirectResponse(_safe_next(next), status_code=303)
    set_session_cookie(response, cookie)
    return response


@router.post("/logout", dependencies=[Depends(verify_csrf), Depends(require_user)])
def logout():
    response = RedirectResponse("/", status_code=303)
    clear_session_cookie(response)
    return response


def _safe_next(target: str) -> str:
    """Only ever redirect to a path on this site — blocks open-redirect phishing."""
    if not target.startswith("/") or target.startswith("//"):
        return "/"
    return target

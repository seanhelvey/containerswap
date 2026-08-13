from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ratelimit
from app.auth import (
    clear_session_cookie,
    hash_password,
    issue_session,
    normalize_username,
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
    username: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    name = normalize_username(username)
    error = validate_credentials(name, password)
    if error is None:
        exists = db.execute(select(User).where(User.username == name)).scalar_one_or_none()
        if exists:
            error = "auth.error.username_taken"

    if error:
        return render(
            request, "signup.html", {"error_key": error, "username": name}, status_code=400
        )

    user = User(username=name, password_hash=hash_password(password))
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
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    name = normalize_username(username)
    user = db.execute(select(User).where(User.username == name)).scalar_one_or_none()

    # Same generic message either way: never reveal whether a username exists.
    if not user or not user.is_active or not verify_password(user.password_hash, password):
        return render(
            request,
            "login.html",
            {"error_key": "auth.error.invalid", "username": name, "next": _safe_next(next)},
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

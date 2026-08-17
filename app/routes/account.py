from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ratelimit
from app.auth import (
    clear_session_cookie,
    generate_display_name,
    hash_password,
    issue_email_verification_token,
    issue_password_reset_token,
    issue_session,
    normalize_display_name,
    normalize_email,
    read_email_verification_token,
    require_user,
    resolve_password_reset_token,
    set_session_cookie,
    validate_credentials,
    validate_password,
    verify_csrf,
    verify_password,
)
from app.db import get_db
from app.email import notify_password_reset, notify_verify_email
from app.models import User
from app.templating import render

router = APIRouter()


@router.get("/account")
def account_page(request: Request, user: User = Depends(require_user)):
    return render(request, "account.html")


@router.get("/signup")
def signup_form(request: Request):
    if getattr(request.state, "user", None):
        return RedirectResponse("/", status_code=303)
    return render(request, "signup.html")


@router.post("/signup", dependencies=[Depends(ratelimit.limiter("signup"))])
def signup(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(""),
    password: str = Form(""),
    display_name: str = Form(""),
    website: str = Form(""),
    steward_interest: str = Form(""),
    db: Session = Depends(get_db),
):
    if website:
        # Honeypot: a hidden field no human reaches. A scripted bot that fills
        # every input trips it. Respond exactly like a real signup so nothing
        # about the response tells the bot it was caught.
        return RedirectResponse("/", status_code=303)

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

    user = User(
        email=address,
        display_name=chosen,
        password_hash=hash_password(password),
        steward_interest=bool(steward_interest),
    )
    db.add(user)
    db.commit()

    # Unverified accounts can use the site immediately. Nothing currently depends
    # on email_verified — password reset proves ownership on its own, the same way.
    background_tasks.add_task(
        notify_verify_email, user.email, issue_email_verification_token(user.id)
    )

    cookie, _ = issue_session(user)
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

    cookie, _ = issue_session(user)
    response = RedirectResponse(_safe_next(next), status_code=303)
    set_session_cookie(response, cookie)
    return response


@router.get("/verify-email/{token}")
def verify_email(request: Request, token: str, db: Session = Depends(get_db)):
    uid = read_email_verification_token(token)
    user = db.get(User, uid) if uid is not None else None
    if user is None:
        return render(request, "verify_email.html", {"success": False}, status_code=400)

    user.email_verified = True
    db.commit()
    return render(request, "verify_email.html", {"success": True})


@router.post(
    "/resend-verification",
    dependencies=[Depends(verify_csrf), Depends(ratelimit.limiter("resend_verification"))],
)
def resend_verification(
    background_tasks: BackgroundTasks,
    next: str = Form("/"),
    user: User = Depends(require_user),
):
    if not user.email_verified:
        background_tasks.add_task(
            notify_verify_email, user.email, issue_email_verification_token(user.id)
        )
    target = _safe_next(next)
    sep = "&" if "?" in target else "?"
    return RedirectResponse(f"{target}{sep}resent=1", status_code=303)


@router.get("/forgot-password")
def forgot_password_form(request: Request):
    return render(request, "forgot_password.html")


@router.post("/forgot-password", dependencies=[Depends(ratelimit.limiter("forgot_password"))])
def forgot_password(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(""),
    db: Session = Depends(get_db),
):
    address = normalize_email(email)
    user = db.execute(select(User).where(User.email == address)).scalar_one_or_none()
    if user and user.is_active:
        background_tasks.add_task(
            notify_password_reset, user.email, issue_password_reset_token(user)
        )
    # Same response either way: never reveal whether an account exists.
    return render(request, "forgot_password.html", {"sent": True})


@router.get("/reset-password/{token}")
def reset_password_form(request: Request, token: str, db: Session = Depends(get_db)):
    user = resolve_password_reset_token(token, db)
    if user is None:
        return render(request, "reset_password.html", {"valid": False}, status_code=400)
    return render(request, "reset_password.html", {"valid": True, "token": token})


@router.post("/reset-password/{token}", dependencies=[Depends(ratelimit.limiter("reset_password"))])
def reset_password(
    request: Request, token: str, password: str = Form(""), db: Session = Depends(get_db)
):
    user = resolve_password_reset_token(token, db)
    if user is None:
        return render(request, "reset_password.html", {"valid": False}, status_code=400)

    error = validate_password(password)
    if error:
        return render(
            request,
            "reset_password.html",
            {"valid": True, "token": token, "error_key": error},
            status_code=400,
        )

    user.password_hash = hash_password(password)
    user.session_version += 1
    # Clicking a link only the account's inbox could have received is itself proof
    # of ownership — the same proof email verification exists to get.
    user.email_verified = True
    db.commit()

    cookie, _ = issue_session(user)
    response = RedirectResponse("/", status_code=303)
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

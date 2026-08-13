"""Username + password auth over a signed cookie session.

Login is by username. Email is collected but optional, and is never rendered
anywhere — it is there so we can tell someone a message is waiting and so they can
recover an account. Not collecting it at all would be a smaller attack surface, but
it would also mean a seller never learns a buyer wrote to them, which is the
difference between a marketplace and a wall of dead listings.

NOT fastapi-users, deliberately. Its routers are JSON-API shaped: they return
tokens and JSON errors, where every flow in this app is an HTML form that needs a
303 and a re-rendered page with an error on it. We would end up writing these two
routes by hand anyway and using fastapi-users only for the password and token
helpers below. Its real value — email verification, reset tokens, OAuth providers —
is worth adopting the day we send our first email, and that swap is contained to
this module plus app/routes/account.py.
"""

import hmac
import re
import secrets
import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User

SESSION_COOKIE = "cs_session"
USERNAME_MIN, USERNAME_MAX = 3, 32
PASSWORD_MIN, PASSWORD_MAX = 10, 200

_hasher = PasswordHasher()
_serializer = URLSafeTimedSerializer(settings.secret_key, salt="containerswap.session")


# --- passwords ---------------------------------------------------------------


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


def normalize_username(raw: str) -> str:
    # NFKC first so visually identical usernames cannot be registered twice.
    return unicodedata.normalize("NFKC", raw or "").strip().lower()


def normalize_email(raw: str) -> str | None:
    """Empty stays empty — an address is optional, and blank is a valid answer."""
    value = (raw or "").strip().lower()
    return value or None


# Deliberately permissive. The only address that really validates is one that
# receives mail, so the check here just catches typos and obvious junk.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


def validate_credentials(username: str, password: str, email: str | None = None) -> str | None:
    """Returns an i18n error key, or None when the credentials are acceptable."""
    if not (USERNAME_MIN <= len(username) <= USERNAME_MAX):
        return "auth.error.username_length"
    if not all(c.isalnum() or c in "._-" for c in username):
        return "auth.error.username_chars"
    if not (PASSWORD_MIN <= len(password) <= PASSWORD_MAX):
        return "auth.error.password_length"
    if email is not None and (len(email) > 255 or not _EMAIL_RE.match(email)):
        return "auth.error.email_invalid"
    return None


# --- sessions ----------------------------------------------------------------


def issue_session(user_id: int) -> tuple[str, str]:
    """Returns (cookie_value, csrf_token). The CSRF token rides inside the signed
    cookie, so a forged cross-site POST cannot know it."""
    csrf = secrets.token_urlsafe(24)
    return _serializer.dumps({"uid": user_id, "csrf": csrf}), csrf


def read_session(request: Request) -> dict | None:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        data = _serializer.loads(raw, max_age=settings.session_max_age_s)
    except (BadSignature, SignatureExpired):
        return None
    return data if isinstance(data, dict) and "uid" in data else None


def set_session_cookie(response, value: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        value,
        max_age=settings.session_max_age_s,
        httponly=True,
        samesite="lax",
        secure=not settings.debug,
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


# --- dependencies ------------------------------------------------------------


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    session = read_session(request)
    if not session:
        return None
    user = db.execute(select(User).where(User.id == session["uid"])).scalar_one_or_none()
    return user if user and user.is_active else None


def require_user(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        # Handled by the exception handler in main.py, which redirects to /login.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


async def verify_csrf(request: Request) -> None:
    """Every state-changing POST depends on this."""
    session = read_session(request)
    expected = (session or {}).get("csrf")
    form = await request.form()
    supplied = str(form.get("csrf_token") or "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf_failed")

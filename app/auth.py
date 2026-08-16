"""Email + password auth over a signed cookie session.

Signup is two fields. Email is the identity: it logs you in, receives the "someone
messaged you" mail, and recovers the account — and is never rendered anywhere. The
public label people see on a listing is `display_name`, which we generate, so there
is no "that username is taken" dance at the moment someone is deciding whether to
bother signing up at all.

NOT fastapi-users, deliberately. Its routers are JSON-API shaped: they return
tokens and JSON errors, where every flow in this app is an HTML form that needs a
303 and a re-rendered page with an error on it. We would end up writing these two
routes by hand anyway and using fastapi-users only for the password and token
helpers below. Its real value — email verification, reset tokens, OAuth providers —
is worth adopting the day we send our first email, and that swap is contained to
this module plus app/routes/account.py.
"""

import hashlib
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
NAME_MIN, NAME_MAX = 2, 32
PASSWORD_MIN, PASSWORD_MAX = 10, 200

_hasher = PasswordHasher()
_serializer = URLSafeTimedSerializer(settings.secret_key, salt="containerswap.session")
# A distinct salt per token type, so a verification token, a reset token, and a
# session cookie can never be swapped for one another even though all three are
# itsdangerous values signed with the same secret_key.
_verify_serializer = URLSafeTimedSerializer(settings.secret_key, salt="containerswap.verify-email")
VERIFY_TOKEN_MAX_AGE_S = 60 * 60 * 24 * 7
_reset_serializer = URLSafeTimedSerializer(settings.secret_key, salt="containerswap.reset-password")
# Short-lived: this token can change a password, not just prove an address.
RESET_TOKEN_MAX_AGE_S = 60 * 60


# --- passwords ---------------------------------------------------------------


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


def normalize_display_name(raw: str) -> str:
    # NFKC so two visually identical names cannot both be registered.
    return unicodedata.normalize("NFKC", raw or "").strip()


def normalize_email(raw: str) -> str:
    return (raw or "").strip().lower()


# Deliberately plain words: a generated name should read like a person chose it
# badly, not like a serial number.
_NAME_WORDS = (
    "jar",
    "crate",
    "tub",
    "lid",
    "basket",
    "kettle",
    "spoon",
    "pantry",
    "sprout",
    "basil",
    "clover",
    "fern",
    "cedar",
    "otter",
    "heron",
    "moss",
)


def generate_display_name(taken: set[str]) -> str:
    """A public label nobody had to invent. Collisions just try again."""
    for _ in range(50):
        candidate = f"{secrets.choice(_NAME_WORDS)}-{secrets.randbelow(9000) + 1000}"
        if candidate not in taken:
            return candidate
    return f"swapper-{secrets.token_hex(4)}"


# Deliberately permissive. The only address that really validates is one that
# receives mail, so the check here just catches typos and obvious junk.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


def validate_password(password: str) -> str | None:
    """Returns an i18n error key, or None when the password is acceptable."""
    if not (PASSWORD_MIN <= len(password) <= PASSWORD_MAX):
        return "auth.error.password_length"
    return None


def validate_credentials(email: str, password: str, display_name: str = "") -> str | None:
    """Returns an i18n error key, or None when the credentials are acceptable."""
    if not email or len(email) > 255 or not _EMAIL_RE.match(email):
        return "auth.error.email_invalid"
    error = validate_password(password)
    if error:
        return error
    if display_name:
        if not (NAME_MIN <= len(display_name) <= NAME_MAX):
            return "auth.error.name_length"
        if "@" in display_name:
            # Stops someone making their public label look like somebody's address.
            return "auth.error.name_chars"
    return None


# --- sessions ----------------------------------------------------------------


def issue_session(user: User) -> tuple[str, str]:
    """Returns (cookie_value, csrf_token). The CSRF token rides inside the signed
    cookie, so a forged cross-site POST cannot know it.

    Carries user.session_version, bumped on password reset, so that resetting a
    password also signs out every other session for the account — the scenario a
    reset exists for is someone else already being logged in as you."""
    csrf = secrets.token_urlsafe(24)
    payload = {"uid": user.id, "csrf": csrf, "v": user.session_version}
    return _serializer.dumps(payload), csrf


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


# --- email verification --------------------------------------------------------


def issue_email_verification_token(user_id: int) -> str:
    return _verify_serializer.dumps({"uid": user_id})


def read_email_verification_token(token: str) -> int | None:
    try:
        data = _verify_serializer.loads(token, max_age=VERIFY_TOKEN_MAX_AGE_S)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid") if isinstance(data, dict) else None
    return uid if isinstance(uid, int) else None


# --- password reset ------------------------------------------------------------


def _password_fingerprint(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def issue_password_reset_token(user: User) -> str:
    """Bound to the current password hash, so the link stops working the moment
    it's used (or the password changes any other way) — no token table needed to
    make it single-use."""
    fp = _password_fingerprint(user.password_hash)
    return _reset_serializer.dumps({"uid": user.id, "fp": fp})


def resolve_password_reset_token(token: str, db: Session) -> User | None:
    try:
        data = _reset_serializer.loads(token, max_age=RESET_TOKEN_MAX_AGE_S)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid") if isinstance(data, dict) else None
    if not isinstance(uid, int):
        return None
    user = db.execute(select(User).where(User.id == uid)).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    expected = _password_fingerprint(user.password_hash)
    if not hmac.compare_digest(str(data.get("fp", "")), expected):
        return None
    return user


# --- dependencies ------------------------------------------------------------


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    session = read_session(request)
    if not session:
        return None
    user = db.execute(select(User).where(User.id == session["uid"])).scalar_one_or_none()
    if not user or not user.is_active:
        return None
    if session.get("v", 0) != user.session_version:
        return None
    return user


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

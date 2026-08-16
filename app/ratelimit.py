"""A Postgres-backed rate limiter.

Was in-memory, which cost no infrastructure but under-counted across FastAPI
Cloud's multiple instances and forgot everything on a restart. Postgres is
already the one piece of real infrastructure this app has, so it is the
shared backend, rather than adding a new one (Redis, etc.) for a limiter
this small.
"""

from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import RateLimitHit

# bucket -> (max events, window seconds)
LIMITS: dict[str, tuple[int, int]] = {
    "signup": (5, 3600),
    "login": (10, 900),
    "listing": (10, 3600),
    "contact": (20, 3600),
    "report": (10, 3600),
    "forgot_password": (5, 3600),
    "reset_password": (10, 3600),
}


def client_key(request: Request) -> str:
    # FastAPI Cloud terminates TLS upstream, so trust the first hop it forwards.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check(db: Session, request: Request, bucket: str) -> None:
    limit, window = LIMITS[bucket]
    key = client_key(request)
    cutoff = datetime.now(UTC) - timedelta(seconds=window)

    # Expired hits for this key are deleted on every check rather than by a separate
    # cleanup job, so the table never accumulates more than LIMITS worth of rows per
    # active key — no cron, no unbounded growth.
    db.execute(
        delete(RateLimitHit).where(
            RateLimitHit.bucket == bucket,
            RateLimitHit.client_key == key,
            RateLimitHit.created_at < cutoff,
        )
    )
    count = db.scalar(
        select(func.count()).where(
            RateLimitHit.bucket == bucket,
            RateLimitHit.client_key == key,
        )
    )
    if count and count >= limit:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait a while and try again.",
        )
    db.add(RateLimitHit(bucket=bucket, client_key=key))
    db.commit()


def limiter(bucket: str):
    def _dependency(request: Request, db: Session = Depends(get_db)) -> None:
        check(db, request, bucket)

    return _dependency

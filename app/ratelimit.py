"""A small in-process rate limiter.

Good enough for a single-instance v1 and it costs no infrastructure. If the app is
ever scaled past one worker this needs to move to shared storage — until then, this
is the honest simplest thing that blunts signup floods and contact-form spam.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

_hits: dict[str, deque[float]] = defaultdict(deque)

# bucket -> (max events, window seconds)
LIMITS: dict[str, tuple[int, int]] = {
    "signup": (5, 3600),
    "login": (10, 900),
    "listing": (10, 3600),
    "contact": (20, 3600),
    "report": (10, 3600),
}


def client_key(request: Request) -> str:
    # FastAPI Cloud terminates TLS upstream, so trust the first hop it forwards.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check(request: Request, bucket: str) -> None:
    limit, window = LIMITS[bucket]
    key = f"{bucket}:{client_key(request)}"
    now = time.monotonic()
    events = _hits[key]
    while events and now - events[0] > window:
        events.popleft()
    if len(events) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait a while and try again.",
        )
    events.append(now)


def limiter(bucket: str):
    def _dependency(request: Request) -> None:
        check(request, bucket)

    return _dependency


def reset() -> None:
    _hits.clear()

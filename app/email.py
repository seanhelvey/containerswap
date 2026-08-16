"""Transactional email, via Resend's HTTP API.

Chosen because it is a plain POST — no SMTP library, and httpx is already a
dependency for object storage. Unset credentials disable sending entirely, which is
what local development wants: no configuration, no accidental mail to real people.

Two rules shape everything here:

Nobody's address is ever exposed. Addresses are read from the database and handed
straight to Resend. They never appear in a log line, an error message, or a rendered
page — that is the promise in SECURITY.md, and a logged "sent to alice@..." would
break it just as surely as printing it on a listing.

Sending never breaks the thing it is reporting on. A failed notification must not
cost someone the message they just wrote, so every failure is swallowed and logged.
Callers run these through BackgroundTasks, after the response is already committed.
"""

import functools
import logging
import os
import webbrowser
from collections.abc import Callable
from typing import ParamSpec

import httpx

from app.config import settings

logger = logging.getLogger("containerswap")

_ENDPOINT = "https://api.resend.com/emails"
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

P = ParamSpec("P")


def _never_fails(func: Callable[P, None]) -> Callable[P, None]:
    """Swallow everything this function can throw.

    These run as BackgroundTasks, and Starlette propagates an exception raised there
    up the ASGI stack after the response has gone out — so an unhandled error in a
    notification surfaces as a broken request for something that actually succeeded.
    The message is already committed by the time we get here; failing to announce it
    is not worth telling the user their message was lost.
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> None:
        try:
            func(*args, **kwargs)
        except Exception:
            logger.exception("notification failed: %s", func.__name__)

    return wrapper


def _send(to: str, subject: str, body: str, link: str | None = None) -> None:
    """Send one plain-text email. Never raises."""
    if not settings.email_enabled:
        # Local development. Print the whole thing to the console instead of sending
        # it, so clicking through a flow shows what the user would have received —
        # a silent no-op makes notifications untestable without a mail provider.
        # Safe here because it only happens when no credentials are configured, which
        # is never true in production.
        # Still no address, even here. "Only in development" is how that rule starts
        # being negotiable, and the body alone is enough to see the flow worked.
        logger.warning(
            "email not configured — would have sent:\n  subject: %s\n\n%s\n", subject, body
        )
        # Opt-in convenience, off by default: skips the "copy the link out of the
        # terminal" step for flows that block on clicking one. Guarded on
        # PYTEST_CURRENT_TEST too, so a developer's own CS_DEV_AUTO_OPEN_LINKS=true
        # in their .env can't pop up a browser mid test-run.
        if link and settings.dev_auto_open_links and "PYTEST_CURRENT_TEST" not in os.environ:
            webbrowser.open(link)
        return

    try:
        response = httpx.post(
            _ENDPOINT,
            json={
                "from": settings.email_from,
                "to": [to],
                "subject": subject,
                "text": body,
            },
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        logger.warning("email send failed: %s", type(exc).__name__)
        return

    if response.is_error:
        # Status and Resend's error body only. The body echoes the subject but never
        # the API key, which travels in a header.
        logger.warning("email rejected with %s: %s", response.status_code, response.text[:200])


@_never_fails
def notify_new_message(recipient_email: str, sender_name: str, listing_title: str) -> None:
    """Tell a seller that someone asked about their listing.

    The message body is deliberately not included. It would put user-written content
    into an email we cannot moderate, and the point is only to bring them back to
    the inbox where the conversation lives.
    """
    _send(
        recipient_email,
        f"Someone asked about your {listing_title}",
        f'{sender_name} sent you a message about "{listing_title}".\n\n'
        f"Read it and reply here: {settings.site_url}/inbox\n\n"
        f"— {settings.site_name}",
    )


@_never_fails
def notify_verify_email(to: str, token: str) -> None:
    """Send the link that proves an address is real and reachable."""
    link = f"{settings.site_url}/verify-email/{token}"
    _send(
        to,
        "Confirm your email",
        f"Confirm your email to finish setting up your account:\n\n"
        f"{link}\n\n"
        f"If you did not sign up for {settings.site_name}, ignore this message.",
        link=link,
    )


@_never_fails
def notify_password_reset(to: str, token: str) -> None:
    """Send the link that lets someone set a new password.

    No email-verification check gates this: successfully clicking the link is
    itself proof the recipient controls the inbox, which is the same proof
    verification exists to get.
    """
    link = f"{settings.site_url}/reset-password/{token}"
    _send(
        to,
        "Reset your password",
        f"Someone (hopefully you) asked to reset your {settings.site_name} password:\n\n"
        f"{link}\n\n"
        f"This link expires in an hour and works once. If you did not request this, "
        f"ignore it and your password will stay the same.",
        link=link,
    )


@_never_fails
def notify_new_report(listing_id: int, listing_title: str, reason: str) -> None:
    """Tell the operator that a listing was reported.

    Without this, reports accumulate in a table nobody reads. No reporter identity is
    included: knowing who complained is not needed to judge the listing, and leaving
    it out keeps the operator's view of a report free of personal data.
    """
    if not settings.report_email:
        logger.warning("listing %s was reported but CS_REPORT_EMAIL is unset", listing_id)
        return

    _send(
        settings.report_email,
        f"Listing reported: {listing_title}",
        f"Listing {listing_id} was reported.\n\n"
        f"Reason given:\n{reason or '(none)'}\n\n"
        f"{settings.site_url}/listings/{listing_id}",
    )


@_never_fails
def notify_new_feedback(message: str, contact_email: str) -> None:
    """Tell the operator that someone left beta feedback.

    Reuses CS_REPORT_EMAIL rather than a feedback-specific setting — one operator,
    one inbox, for as long as that's true. contact_email is whatever the person
    chose to type in, not a User.email — voluntary, given so the operator can
    reply, and only ever seen here.
    """
    if not settings.report_email:
        logger.warning("feedback was submitted but CS_REPORT_EMAIL is unset")
        return

    _send(
        settings.report_email,
        "New beta feedback",
        f"{message}\n\nReply to: {contact_email or '(not given)'}",
    )

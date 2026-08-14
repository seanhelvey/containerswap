"""Where processed images are kept.

Two backends, both of which really exist: local disk for development, Supabase
Storage in production. Production has no persistent volume, so a file written to
local disk there is gone at the next redeploy — the object store is not an
optimisation, it is the only thing that survives.

The bucket is public. That is not an oversight: the home page, the map and
/api/listings.geojson all serve listing photos to signed-out visitors, so a signed
URL would protect nothing while breaking CDN and browser caching. What makes the
photos safe to publish is upstream, in images.process_upload, which rebuilds every
image from raw pixels and so cannot carry EXIF GPS.
"""

import base64
import binascii
import json

import httpx

from app.config import settings

# Uploads are one small PUT; a slow object store must not pin a worker for a minute.
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class StorageError(Exception):
    """The object store rejected a write or delete."""


def describe_key() -> str:
    """Name the *kind* of key configured, never the key itself.

    Uploads write a row into storage.objects, which is under row-level security.
    Only service_role bypasses that, so an anon or publishable key fails with
    "new row violates row-level security policy" — an error that says nothing about
    which key is loaded. The role sits in the JWT payload, which is not a secret:
    it is base64, not encryption, and the signature is what makes the key usable.
    """
    key = settings.supabase_service_key
    if not key:
        return "missing"
    if key.startswith("sb_publishable_"):
        return "publishable (cannot write — this is the anon-equivalent key)"
    if key.startswith("sb_secret_"):
        return "sb_secret_ (new-style secret key)"

    parts = key.split(".")
    if len(parts) != 3:
        return "unrecognised format"
    try:
        segment = parts[1] + "=" * (-len(parts[1]) % 4)
        role = json.loads(base64.urlsafe_b64decode(segment)).get("role")
    except (ValueError, binascii.Error):
        return "malformed JWT"
    return f"JWT role={role!r}"


def save(payload: bytes, filename: str) -> None:
    if not settings.uses_object_storage:
        destination = settings.upload_dir / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return

    try:
        response = httpx.post(
            f"{settings.supabase_url}/storage/v1/object/{settings.storage_bucket}/{filename}",
            content=payload,
            headers={
                "Authorization": f"Bearer {settings.supabase_service_key}",
                "Content-Type": "image/jpeg",
                "Cache-Control": "public, max-age=31536000, immutable",
            },
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        # Timeouts, DNS failures and malformed URLs all land here. They must not
        # reach the route as a raw httpx exception: that renders a 500 and the user
        # loses everything they typed.
        #
        # The host is in the message because the alternative is guessing at a
        # misconfigured CS_SUPABASE_URL from a bare ConnectError. It is safe to log:
        # the service key travels in a header, never in the URL.
        raise StorageError(
            f"upload to {settings.supabase_url} failed: {type(exc).__name__}"
        ) from exc

    if response.is_error:
        # The body is the only thing that distinguishes a missing bucket from a
        # rejected MIME type from a bad key, and Supabase returns a small JSON error
        # object that never echoes request headers — so it is safe to log and the
        # only way to diagnose this without another deploy. Truncated in case a
        # future error page is larger than expected.
        detail = response.text[:300].replace("\n", " ")
        raise StorageError(
            f"upload to bucket {settings.storage_bucket!r} failed with "
            f"{response.status_code}: {detail}"
        )


def delete(filename: str | None) -> None:
    """Remove a stored image, refusing anything that is not a bare filename."""
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        return

    if not settings.uses_object_storage:
        (settings.upload_dir / filename).unlink(missing_ok=True)
        return

    # A failed delete leaves an orphaned object, which is untidy but harmless — never
    # worth failing the user's request over, so this does not raise.
    try:
        httpx.request(
            "DELETE",
            f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{settings.storage_bucket}/{filename}",
            headers={"Authorization": f"Bearer {settings.supabase_service_key}"},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError:
        pass


def url_for(filename: str | None) -> str | None:
    """Public URL for a stored image, or None when the listing has no photo."""
    if not filename:
        return None
    if not settings.uses_object_storage:
        return f"/uploads/{filename}"
    return f"{settings.storage_public_base}/{filename}"

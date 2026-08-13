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

import httpx

from app.config import settings

# Uploads are one small PUT; a slow object store must not pin a worker for a minute.
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class StorageError(Exception):
    """The object store rejected a write or delete."""


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
        raise StorageError(f"upload could not be sent: {type(exc).__name__}") from exc

    if response.is_error:
        # Deliberately no response body in the message: it can echo the request, and
        # the request carried the service key.
        raise StorageError(f"upload failed with {response.status_code}")


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

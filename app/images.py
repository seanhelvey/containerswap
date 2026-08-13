"""Upload handling.

Every uploaded file is decoded, re-encoded, and written under a generated name. That
single round-trip is what buys us safety: it verifies the bytes really are an image,
drops EXIF (including the GPS tags that would otherwise leak the photographer's exact
location), and makes the stored filename impossible to influence from the request.
"""

import secrets
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF"}
# Guards against decompression bombs: a 200MP "image" in a 40KB file.
Image.MAX_IMAGE_PIXELS = 64_000_000


class ImageRejected(Exception):
    """The upload was missing, too large, or not a decodable image."""


def process_upload(raw: bytes) -> str:
    """Validate, strip, downscale and compress. Returns the stored filename.

    Raises ImageRejected for anything we will not store.
    """
    if not raw:
        raise ImageRejected("empty_file")
    if len(raw) > settings.max_upload_bytes:
        raise ImageRejected("too_large")

    try:
        with Image.open(BytesIO(raw)) as img:
            if img.format not in ALLOWED_FORMATS:
                raise ImageRejected("unsupported_format")
            # Honour the orientation tag, then discard all metadata by rebuilding
            # the image from pixels only.
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            img.thumbnail(
                (settings.max_image_px, settings.max_image_px),
                Image.Resampling.LANCZOS,
            )
            clean = Image.new("RGB", img.size)
            clean.putdata(list(img.getdata()))
    except ImageRejected:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageRejected("not_an_image") from exc

    payload = _compress(clean)
    filename = f"{secrets.token_urlsafe(16)}.jpg"
    destination = settings.upload_dir / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return filename


def _compress(img: Image.Image) -> bytes:
    """Walk quality down until the JPEG fits the byte budget."""
    target = settings.target_image_bytes
    payload = b""
    for quality in (85, 75, 65, 55, 45, 35):
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
        payload = buffer.getvalue()
        if len(payload) <= target:
            return payload

    # Still too big at the lowest quality: shrink dimensions and retry once.
    smaller = img.copy()
    smaller.thumbnail((800, 800), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    smaller.save(buffer, format="JPEG", quality=45, optimize=True, progressive=True)
    return buffer.getvalue()


def delete_image(filename: str | None) -> None:
    """Remove a stored image, refusing anything that is not a bare filename."""
    if not filename:
        return
    name = Path(filename).name
    if name != filename:
        return
    (settings.upload_dir / name).unlink(missing_ok=True)

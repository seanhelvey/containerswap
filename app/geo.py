"""Location privacy.

A listing pin should say "this neighbourhood", never "this house". Every coordinate
is jittered by a random offset before it is stored, and the precise value the browser
reported is dropped on the floor — it is never written to the database or a log.
"""

import math
import secrets

from app.config import settings

_M_PER_DEG_LAT = 111_320.0


def fuzz(lat: float, lng: float, radius_m: int | None = None) -> tuple[float, float]:
    """Offset a coordinate by a uniformly-random vector within `radius_m`."""
    radius = settings.location_fuzz_m if radius_m is None else radius_m
    if radius <= 0:
        return round(lat, 5), round(lng, 5)

    # Uniform over the disc: sqrt keeps points from bunching at the centre.
    angle = secrets.randbelow(360_000) / 1000.0 * math.pi / 180.0
    distance = radius * math.sqrt(secrets.randbelow(1_000_000) / 1_000_000)

    d_lat = (distance * math.cos(angle)) / _M_PER_DEG_LAT
    lat_rad = math.radians(lat)
    m_per_deg_lng = _M_PER_DEG_LAT * max(math.cos(lat_rad), 0.01)
    d_lng = (distance * math.sin(angle)) / m_per_deg_lng

    return round(clamp_lat(lat + d_lat), 5), round(wrap_lng(lng + d_lng), 5)


def clamp_lat(lat: float) -> float:
    return max(-90.0, min(90.0, lat))


def wrap_lng(lng: float) -> float:
    return ((lng + 180.0) % 360.0) - 180.0


def parse_coord(raw: str | None, *, lo: float, hi: float) -> float | None:
    """Parse an untrusted lat/lng form field. Returns None for anything unusable."""
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if math.isnan(value) or math.isinf(value) or not (lo <= value <= hi):
        return None
    return value


def parse_latlng(lat_raw: str | None, lng_raw: str | None) -> tuple[float, float] | None:
    lat = parse_coord(lat_raw, lo=-90.0, hi=90.0)
    lng = parse_coord(lng_raw, lo=-180.0, hi=180.0)
    if lat is None or lng is None:
        return None
    return lat, lng

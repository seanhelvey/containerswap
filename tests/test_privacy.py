"""The non-negotiables: nobody's contact details leak, and a pin is not an address."""

from io import BytesIO

import pytest
from PIL import Image

from app.geo import fuzz
from app.images import ImageRejected, process_upload
from app.models import User
from tests.conftest import csrf_for, register


def test_user_model_has_no_contact_columns():
    """The strongest guarantee available: the data simply is not collected."""
    columns = set(User.__table__.columns.keys())
    for forbidden in ("email", "phone", "contact", "address"):
        assert forbidden not in columns


def test_listing_page_never_renders_a_contact_route_for_the_owner(client):
    register(client, "poster")
    token = csrf_for(client)
    client.post(
        "/listings",
        data={"csrf_token": token, "title": "Glass jars", "price": "free"},
        follow_redirects=False,
    )

    page = client.get("/listings/1").text
    # The owner sees admin controls, never a mailto: link or a tel: link.
    assert "mailto:" not in page
    assert "tel:" not in page


def test_contact_message_goes_to_the_inbox_not_to_an_address(client):
    register(client, "owner")
    token = csrf_for(client)
    client.post(
        "/listings",
        data={"csrf_token": token, "title": "Deli tubs"},
        follow_redirects=False,
    )
    client.post("/logout", data={"csrf_token": token}, follow_redirects=False)

    register(client, "buyer")
    buyer_token = csrf_for(client)
    response = client.post(
        "/listings/1/contact",
        data={"csrf_token": buyer_token, "body": "Still available?"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    # The sender never learns anything about the owner beyond their username.
    detail = client.get("/listings/1").text
    assert "mailto:" not in detail

    # The owner finds it in their inbox.
    client.post("/logout", data={"csrf_token": buyer_token}, follow_redirects=False)
    client.post(
        "/login",
        data={"username": "owner", "password": "correct-horse-battery"},
        follow_redirects=False,
    )
    inbox = client.get("/inbox").text
    assert "Still available?" in inbox
    assert "buyer" in inbox


def test_coordinates_are_shifted_before_storage():
    lat, lng = 40.80210, -124.16370
    seen = {fuzz(lat, lng) for _ in range(25)}
    assert (lat, lng) not in seen, "exact coordinates must never survive fuzzing"
    # ...but the shift stays local: a few hundred metres, not a different town.
    for f_lat, f_lng in seen:
        assert abs(f_lat - lat) < 0.01
        assert abs(f_lng - lng) < 0.01


def test_upload_strips_exif_gps(upload_dir):
    """A photo taken on a phone carries GPS tags. Ours must not."""
    source = Image.new("RGB", (900, 700), (120, 160, 130))
    buffer = BytesIO()
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (40.0, 48.0, 7.0)}  # GPSInfo
    source.save(buffer, format="JPEG", exif=exif.tobytes())

    filename = process_upload(buffer.getvalue())
    stored = Image.open(upload_dir / filename)

    assert not stored.getexif(), "stored image still carries metadata"
    assert stored.info.get("exif") is None


def test_upload_rejects_non_images():
    with pytest.raises(ImageRejected):
        process_upload(b"#!/bin/sh\necho not an image\n")

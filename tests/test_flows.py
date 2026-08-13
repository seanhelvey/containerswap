"""The happy paths a v1 has to keep working, plus the auth/CSRF guards."""

from io import BytesIO

from PIL import Image

from app.config import settings
from app.db import SessionLocal
from app.models import EventLog, User
from tests.conftest import csrf_for, register


def event_types() -> list[str]:
    with SessionLocal() as db:
        return [row.event_type for row in db.query(EventLog).order_by(EventLog.id).all()]


def test_home_renders_for_anonymous_visitors(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "ContainerSwap" in response.text


def test_full_listing_lifecycle_logs_every_analytics_event(client):
    register(client, "alice")
    token = csrf_for(client)

    created = client.post(
        "/listings",
        data={
            "csrf_token": token,
            "title": "Yogurt tubs",
            "quantity": "12 assorted",
            "price": "trade for basil starts",
            "category": "yogurt",
            "lat": "40.8021",
            "lng": "-124.1637",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert created.headers["location"] == "/listings/1"

    assert "Yogurt tubs" in client.get("/").text
    assert "trade for basil starts" in client.get("/listings/1").text

    completed = client.post(
        "/listings/1/complete", data={"csrf_token": token}, follow_redirects=False
    )
    assert completed.status_code == 303

    assert event_types() == ["listing_created", "listing_viewed", "listing_completed"]


def test_only_the_owner_can_complete_a_listing(client):
    register(client, "owner")
    token = csrf_for(client)
    client.post("/listings", data={"csrf_token": token, "title": "Jars"}, follow_redirects=False)
    client.post("/logout", data={"csrf_token": token}, follow_redirects=False)

    register(client, "stranger")
    stranger_token = csrf_for(client)
    response = client.post(
        "/listings/1/complete", data={"csrf_token": stranger_token}, follow_redirects=False
    )
    assert response.status_code == 403


def test_posting_without_a_csrf_token_is_rejected(client):
    register(client, "alice")
    response = client.post("/listings", data={"title": "No token"}, follow_redirects=False)
    assert response.status_code == 403


def test_anonymous_visitors_are_sent_to_login(client):
    response = client.get("/listings/new", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/listings/new"


def test_login_does_not_reveal_whether_an_account_exists(client):
    register(client, "alice")
    client.post("/logout", data={"csrf_token": csrf_for(client)}, follow_redirects=False)

    known = client.post("/login", data={"email": "alice@example.com", "password": "wrong-password"})
    unknown = client.post(
        "/login", data={"email": "nobody@example.com", "password": "wrong-password"}
    )
    assert known.status_code == unknown.status_code == 401
    assert "Wrong email or password." in known.text
    assert known.text == unknown.text.replace("nobody@example.com", "alice@example.com")


def test_signup_needs_only_an_email_and_password(client):
    """Two fields. No name to invent, no 'that one is taken'."""
    response = client.post(
        "/signup",
        data={"email": "Someone@Example.com", "password": "correct-horse-battery"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    with SessionLocal() as db:
        user = db.query(User).filter_by(email="someone@example.com").one()
        assert user.display_name, "a public name should have been generated"
        assert "@" not in user.display_name


def test_email_is_case_insensitive_at_login(client):
    register(client, "alice")
    client.post("/logout", data={"csrf_token": csrf_for(client)}, follow_redirects=False)
    response = client.post(
        "/login",
        data={"email": "ALICE@example.com", "password": "correct-horse-battery"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_open_redirect_is_blocked_on_login(client):
    register(client, "alice")
    client.post("/logout", data={"csrf_token": csrf_for(client)}, follow_redirects=False)
    response = client.post(
        "/login",
        data={
            "email": "alice@example.com",
            "password": "correct-horse-battery",
            "next": "//evil.example",
        },
        follow_redirects=False,
    )
    assert response.headers["location"] == "/"


def test_comments_are_public_and_attributed(client):
    register(client, "alice")
    token = csrf_for(client)
    client.post("/listings", data={"csrf_token": token, "title": "Jars"}, follow_redirects=False)
    client.post(
        "/listings/1/comments",
        data={"csrf_token": token, "body": "What size are they?"},
        follow_redirects=False,
    )
    page = client.get("/listings/1").text
    assert "What size are they?" in page
    assert "alice" in page


def test_geojson_exposes_only_public_fields(client):
    register(client, "alice")
    token = csrf_for(client)
    client.post(
        "/listings",
        data={"csrf_token": token, "title": "Jars", "lat": "40.8", "lng": "-124.1"},
        follow_redirects=False,
    )
    feature = client.get("/api/listings.geojson").json()["features"][0]
    assert set(feature["properties"]) == {
        "id",
        "title",
        "price",
        "quantity",
        "category",
        "url",
        "image",
    }


def test_photo_upload_is_shrunk_and_served(client):
    register(client, "alice")
    token = csrf_for(client)

    # A deliberately oversized photo, like one straight off a phone camera.
    big = Image.new("RGB", (4000, 3000))
    for x in range(0, 4000, 7):  # noise, so it does not compress to nothing
        for y in range(0, 3000, 7):
            big.putpixel((x, y), (x % 256, y % 256, (x + y) % 256))
    buffer = BytesIO()
    big.save(buffer, format="JPEG", quality=95)

    response = client.post(
        "/listings",
        data={"csrf_token": token, "title": "Jars with lids"},
        files={"image": ("photo.jpg", buffer.getvalue(), "image/jpeg")},
        follow_redirects=False,
    )
    assert response.status_code == 303

    page = client.get("/listings/1").text
    filename = page.split("/uploads/")[1].split('"')[0]
    stored = settings.upload_dir / filename

    assert stored.stat().st_size <= settings.target_image_bytes
    assert max(Image.open(stored).size) <= settings.max_image_px
    assert client.get(f"/uploads/{filename}").status_code == 200


def test_security_headers_are_present(client):
    headers = client.get("/").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in headers["Content-Security-Policy"]


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_storage_failure_returns_the_form_not_a_500(client, monkeypatch):
    """A broken object store must not cost the user everything they typed.

    Regression test: a malformed CS_SUPABASE_URL raised httpx.UnsupportedProtocol
    straight out of the route, which rendered a 500 and discarded the whole form.
    """
    from app import storage

    def explode(payload, filename):
        raise storage.StorageError("simulated outage")

    monkeypatch.setattr(storage, "save", explode)

    register(client, "alice")
    token = csrf_for(client)

    buffer = BytesIO()
    Image.new("RGB", (64, 64)).save(buffer, format="JPEG")

    response = client.post(
        "/listings",
        data={"csrf_token": token, "title": "Jars with lids", "body": "four of them"},
        files={"image": ("photo.jpg", buffer.getvalue(), "image/jpeg")},
        follow_redirects=False,
    )

    # 400 is what _new_listing_error returns for every form error; the point is that
    # it re-renders rather than 500-ing.
    assert response.status_code == 400, response.status_code
    # Their text survives, so the form can be resubmitted without retyping.
    assert "Jars with lids" in response.text
    assert "four of them" in response.text

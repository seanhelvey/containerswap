"""The happy paths a v1 has to keep working, plus the auth/CSRF guards."""

from io import BytesIO

from PIL import Image
from sqlalchemy.exc import SQLAlchemyError

import main
from app.config import settings
from app.db import SessionLocal, get_db
from app.models import EventLog, Feedback, Listing, Message, User
from tests.conftest import csrf_for, register


def event_types() -> list[str]:
    with SessionLocal() as db:
        return [row.event_type for row in db.query(EventLog).order_by(EventLog.id).all()]


def test_home_renders_for_anonymous_visitors(client):
    response = client.get("/")
    assert response.status_code == 200
    assert settings.site_name in response.text


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


def test_owner_can_toggle_a_listing_as_demo(client):
    """Self-service is_seed toggle, so marking a planted listing doesn't need psql."""
    register(client, "owner")
    token = csrf_for(client)
    client.post("/listings", data={"csrf_token": token, "title": "Jars"}, follow_redirects=False)

    client.post("/listings/1/toggle-demo", data={"csrf_token": token}, follow_redirects=False)
    with SessionLocal() as db:
        assert db.query(Listing).filter_by(id=1).one().is_seed is True

    client.post("/listings/1/toggle-demo", data={"csrf_token": token}, follow_redirects=False)
    with SessionLocal() as db:
        assert db.query(Listing).filter_by(id=1).one().is_seed is False


def test_a_stranger_cannot_toggle_someone_elses_listing_as_demo(client):
    register(client, "owner")
    token = csrf_for(client)
    client.post("/listings", data={"csrf_token": token, "title": "Jars"}, follow_redirects=False)
    client.post("/logout", data={"csrf_token": token}, follow_redirects=False)

    register(client, "stranger")
    response = client.post(
        "/listings/1/toggle-demo", data={"csrf_token": csrf_for(client)}, follow_redirects=False
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


def test_signup_flood_is_rate_limited(client):
    """LIMITS['signup'] is (5, 3600) — the 6th attempt in the window should 429.

    Also the one thing that actually exercises the Postgres-backed limiter rather
    than just trusting the rewrite from in-memory.
    """
    for i in range(5):
        response = client.post(
            "/signup",
            data={"email": f"flood{i}@example.com", "password": "correct-horse-battery"},
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text

    response = client.post(
        "/signup",
        data={"email": "flood5@example.com", "password": "correct-horse-battery"},
        follow_redirects=False,
    )
    assert response.status_code == 429


def test_signup_honeypot_silently_drops_the_account(client):
    """A filled hp-field means a bot filled every input; give it a convincing no-op."""
    response = client.post(
        "/signup",
        data={
            "email": "bot@example.com",
            "password": "correct-horse-battery",
            "website": "http://spam.example",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "cs_session" not in response.cookies

    with SessionLocal() as db:
        assert db.query(User).filter_by(email="bot@example.com").one_or_none() is None


def test_signup_sends_a_verification_link(client, monkeypatch):
    from app.routes import account

    sent: list[tuple] = []
    monkeypatch.setattr(account, "notify_verify_email", lambda *args: sent.append(args))

    # Not register(): that helper marks the account verified for the tests that
    # need one working end to end. This test is about the unverified state itself.
    client.post(
        "/signup",
        data={"email": "alice@example.com", "password": "correct-horse-battery"},
        follow_redirects=False,
    )

    with SessionLocal() as db:
        user = db.query(User).filter_by(email="alice@example.com").one()
        assert user.email_verified is False

    assert len(sent) == 1
    to, token = sent[0]
    assert to == "alice@example.com"

    response = client.get(f"/verify-email/{token}", follow_redirects=False)
    assert response.status_code == 200
    assert "Email verified" in response.text

    with SessionLocal() as db:
        assert db.query(User).filter_by(email="alice@example.com").one().email_verified is True


def test_an_invalid_verification_token_verifies_nobody(client):
    client.post(
        "/signup",
        data={"email": "alice@example.com", "password": "correct-horse-battery"},
        follow_redirects=False,
    )
    response = client.get("/verify-email/not-a-real-token", follow_redirects=False)
    assert response.status_code == 400

    with SessionLocal() as db:
        assert db.query(User).filter_by(email="alice@example.com").one().email_verified is False


def test_unverified_user_sees_a_prompt_instead_of_the_post_form(client):
    client.post(
        "/signup",
        data={"email": "alice@example.com", "password": "correct-horse-battery"},
        follow_redirects=False,
    )
    page = client.get("/listings/new")
    assert page.status_code == 200
    assert 'name="title"' not in page.text


def test_unverified_user_cannot_post_a_listing(client):
    client.post(
        "/signup",
        data={"email": "alice@example.com", "password": "correct-horse-battery"},
        follow_redirects=False,
    )
    token = csrf_for(client, "/")
    response = client.post(
        "/listings", data={"csrf_token": token, "title": "Jars"}, follow_redirects=False
    )
    assert response.status_code == 403

    with SessionLocal() as db:
        assert db.query(Listing).count() == 0


def test_unverified_user_cannot_message_an_owner(client):
    register(client, "owner")
    owner_token = csrf_for(client)
    client.post(
        "/listings", data={"csrf_token": owner_token, "title": "Jars"}, follow_redirects=False
    )
    client.post("/logout", data={"csrf_token": owner_token}, follow_redirects=False)

    client.post(
        "/signup",
        data={"email": "stranger@example.com", "password": "correct-horse-battery"},
        follow_redirects=False,
    )
    detail = client.get("/listings/1")
    assert 'action="/listings/1/contact"' not in detail.text

    token = csrf_for(client, "/")
    response = client.post(
        "/listings/1/contact",
        data={"csrf_token": token, "body": "Still available?"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    with SessionLocal() as db:
        assert db.query(Message).count() == 0


def test_resend_verification_sends_another_token(client, monkeypatch):
    from app.routes import account

    client.post(
        "/signup",
        data={"email": "alice@example.com", "password": "correct-horse-battery"},
        follow_redirects=False,
    )

    sent: list[tuple] = []
    monkeypatch.setattr(account, "notify_verify_email", lambda *args: sent.append(args))
    token = csrf_for(client, "/")
    response = client.post(
        "/resend-verification",
        data={"csrf_token": token, "next": "/"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/?resent=1"
    assert len(sent) == 1
    assert sent[0][0] == "alice@example.com"


def test_forgot_password_does_not_reveal_whether_an_account_exists(client):
    register(client, "alice")
    known = client.post("/forgot-password", data={"email": "alice@example.com"})
    unknown = client.post("/forgot-password", data={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.text == unknown.text


def test_password_reset_changes_the_password_and_signs_in(client, monkeypatch):
    from app.routes import account

    register(client, "alice")

    sent: list[tuple] = []
    monkeypatch.setattr(account, "notify_password_reset", lambda *args: sent.append(args))
    client.post("/forgot-password", data={"email": "alice@example.com"})
    assert len(sent) == 1
    to, token = sent[0]
    assert to == "alice@example.com"

    form = client.get(f"/reset-password/{token}", follow_redirects=False)
    assert form.status_code == 200

    response = client.post(
        f"/reset-password/{token}", data={"password": "new-correct-horse"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert "cs_session" in response.cookies

    client.cookies.clear()
    old_password = client.post(
        "/login", data={"email": "alice@example.com", "password": "correct-horse-battery"}
    )
    assert old_password.status_code == 401

    new_password = client.post(
        "/login",
        data={"email": "alice@example.com", "password": "new-correct-horse"},
        follow_redirects=False,
    )
    assert new_password.status_code == 303

    with SessionLocal() as db:
        assert db.query(User).filter_by(email="alice@example.com").one().email_verified is True


def test_password_reset_signs_out_other_sessions(client, monkeypatch):
    """The scenario a reset exists for is someone else already being logged in as you."""
    from fastapi.testclient import TestClient

    from app.routes import account

    register(client, "alice")
    with TestClient(main.app) as other:
        other.post(
            "/login", data={"email": "alice@example.com", "password": "correct-horse-battery"}
        )
        assert other.get("/listings/new").status_code == 200

        sent: list[tuple] = []
        monkeypatch.setattr(account, "notify_password_reset", lambda *args: sent.append(args))
        client.post("/forgot-password", data={"email": "alice@example.com"})
        _, token = sent[0]
        client.post(f"/reset-password/{token}", data={"password": "new-correct-horse"})

        still_logged_in = other.get("/listings/new", follow_redirects=False)
        assert still_logged_in.status_code == 303
        assert still_logged_in.headers["location"] == "/login?next=/listings/new"


def test_password_reset_token_can_only_be_used_once(client, monkeypatch):
    from app.routes import account

    register(client, "alice")
    sent: list[tuple] = []
    monkeypatch.setattr(account, "notify_password_reset", lambda *args: sent.append(args))
    client.post("/forgot-password", data={"email": "alice@example.com"})
    _, token = sent[0]

    first = client.post(
        f"/reset-password/{token}", data={"password": "new-correct-horse"}, follow_redirects=False
    )
    assert first.status_code == 303

    replay = client.post(f"/reset-password/{token}", data={"password": "another-password"})
    assert replay.status_code == 400


def test_reset_password_rejects_a_short_password(client, monkeypatch):
    from app.routes import account

    register(client, "alice")
    sent: list[tuple] = []
    monkeypatch.setattr(account, "notify_password_reset", lambda *args: sent.append(args))
    client.post("/forgot-password", data={"email": "alice@example.com"})
    _, token = sent[0]

    response = client.post(f"/reset-password/{token}", data={"password": "short"})
    assert response.status_code == 400

    login = client.post(
        "/login",
        data={"email": "alice@example.com", "password": "correct-horse-battery"},
        follow_redirects=False,
    )
    assert login.status_code == 303


def test_an_invalid_reset_token_changes_nothing(client):
    response = client.get("/reset-password/not-a-real-token", follow_redirects=False)
    assert response.status_code == 400
    response = client.post(
        "/reset-password/not-a-real-token", data={"password": "new-correct-horse"}
    )
    assert response.status_code == 400


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


def test_contacting_an_owner_notifies_them(client, monkeypatch):
    """The inbox is not enough on its own — nobody checks a site they forgot about."""
    from app import email

    sent: list[tuple] = []
    monkeypatch.setattr(email, "notify_new_message", lambda *args: sent.append(args))

    register(client, "owner")
    token = csrf_for(client)
    client.post("/listings", data={"csrf_token": token, "title": "Jars"}, follow_redirects=False)
    client.post("/logout", data={"csrf_token": token}, follow_redirects=False)

    register(client, "buyer")
    client.post(
        "/listings/1/contact",
        data={"csrf_token": csrf_for(client), "body": "Are these still going?"},
        follow_redirects=False,
    )

    assert len(sent) == 1, "the owner should have been notified exactly once"
    recipient, sender_name, title = sent[0]
    assert recipient == "owner@example.com"
    assert sender_name == "buyer"
    assert title == "Jars"


def test_a_report_reaches_a_human(client, monkeypatch):
    """The page says "we will take a look", so a report must leave the database."""
    from app import email

    sent: list[tuple] = []
    monkeypatch.setattr(email, "notify_new_report", lambda *args: sent.append(args))

    register(client, "owner")
    token = csrf_for(client)
    client.post("/listings", data={"csrf_token": token, "title": "Jars"}, follow_redirects=False)
    client.post("/logout", data={"csrf_token": token}, follow_redirects=False)

    register(client, "reporter")
    client.post(
        "/listings/1/report",
        data={"csrf_token": csrf_for(client), "reason": "not food safe"},
        follow_redirects=False,
    )

    assert sent == [(1, "Jars", "not food safe")]


def test_feedback_reaches_a_human_without_an_account(client, monkeypatch):
    """Feedback has to work signed out — that's often when people notice something
    confusing, before they've made an account at all."""
    from app import email

    sent: list[tuple] = []
    monkeypatch.setattr(email, "notify_new_feedback", lambda *args: sent.append(args))

    response = client.post(
        "/feedback",
        data={"message": "the map is confusing", "contact_email": "me@example.com"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/feedback?sent=1"
    assert sent == [("the map is confusing", "me@example.com")]

    with SessionLocal() as db:
        row = db.query(Feedback).one()
        assert row.user_id is None
        assert row.contact_email == "me@example.com"


def test_feedback_honeypot_silently_drops_it(client):
    """A filled hp-field means a bot filled every input; give it a convincing no-op."""
    response = client.post(
        "/feedback",
        data={"message": "buy cheap watches", "website": "http://spam.example"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/feedback?sent=1"

    with SessionLocal() as db:
        assert db.query(Feedback).count() == 0


def test_feedback_flood_is_rate_limited(client):
    """LIMITS['feedback'] is (10, 3600) — the 11th attempt in the window should 429."""
    for i in range(10):
        response = client.post("/feedback", data={"message": f"note {i}"}, follow_redirects=False)
        assert response.status_code == 303, response.text

    response = client.post("/feedback", data={"message": "one too many"}, follow_redirects=False)
    assert response.status_code == 429


def test_a_mail_outage_does_not_lose_the_message(client, monkeypatch):
    """Notification is a side effect. Failing it must not fail the thing it reports."""
    from app import email

    def explode(*args, **kwargs):
        raise RuntimeError("mail provider down")

    # Patch the sender, not notify_new_message, so the real guard is what is tested.
    monkeypatch.setattr(email, "_send", explode)

    register(client, "owner")
    token = csrf_for(client)
    client.post("/listings", data={"csrf_token": token, "title": "Jars"}, follow_redirects=False)
    client.post("/logout", data={"csrf_token": token}, follow_redirects=False)

    register(client, "buyer")
    response = client.post(
        "/listings/1/contact",
        data={"csrf_token": csrf_for(client), "body": "Are these still going?"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    # The message is in the owner's inbox regardless of what the mailer did.
    client.post("/logout", data={"csrf_token": csrf_for(client)}, follow_redirects=False)
    client.post(
        "/login",
        data={"email": "owner@example.com", "password": "correct-horse-battery"},
        follow_redirects=False,
    )
    assert "Are these still going?" in client.get("/inbox").text


def test_comments_are_gone(client):
    """The public Q&A channel was removed; only private messages remain."""
    register(client, "alice")
    token = csrf_for(client)
    client.post("/listings", data={"csrf_token": token, "title": "Jars"}, follow_redirects=False)

    posted = client.post(
        "/listings/1/comments",
        data={"csrf_token": token, "body": "What size are they?"},
        follow_redirects=False,
    )
    assert posted.status_code == 405 or posted.status_code == 404
    assert "comments" not in client.get("/listings/1").text


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


def test_healthz_reports_a_database_outage(client):
    """The whole point of a DB check is to stop being green during an outage."""

    class ExplodingSession:
        def execute(self, *args, **kwargs):
            raise SQLAlchemyError("db is down")

    main.app.dependency_overrides[get_db] = lambda: ExplodingSession()
    try:
        response = client.get("/healthz")
    finally:
        del main.app.dependency_overrides[get_db]
    assert response.status_code == 503
    assert response.json() == {"status": "error"}


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


def test_new_listing_offers_a_map_not_coordinate_boxes(client):
    """Nobody knows their own latitude, so the form must never ask for it."""
    register(client, "alice")
    page = client.get("/listings/new").text

    assert 'id="pick-map"' in page, "the location picker map is missing"
    assert 'type="hidden" name="lat"' in page, "lat should be machine-written, not typed"
    assert 'type="hidden" name="lng"' in page, "lng should be machine-written, not typed"
    assert "latitude" not in page, "a visible latitude input is back"
    assert "leaflet.js" in page, "picker needs Leaflet loaded on this page"


def test_csp_allows_the_tile_host_the_javascript_actually_uses(client):
    """Regression: `*.tile.openstreetmap.org` does not match the bare host, so every
    tile was blocked and the map rendered as an empty grey box."""
    from pathlib import Path

    csp = client.get("/").headers["Content-Security-Policy"]
    img_src = next(part for part in csp.split(";") if part.strip().startswith("img-src"))

    for js in ("map.js", "mini-map.js", "new-listing.js"):
        source = Path("static/js", js).read_text()
        if "tile.openstreetmap.org" not in source:
            continue
        assert "https://tile.openstreetmap.org" in img_src, f"{js} tiles blocked by CSP"

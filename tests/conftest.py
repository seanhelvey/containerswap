import importlib
import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

# Point the app at a throwaway data directory before anything imports settings.
_TMP = tempfile.mkdtemp(prefix="containerswap-tests-")
os.environ["CS_DATA_DIR"] = _TMP
os.environ["CS_SECRET_KEY"] = "test-secret-key-not-used-in-production"
os.environ["CS_DEBUG"] = "true"

import app.config  # noqa: E402


def _use_a_separate_test_database() -> None:
    """Redirect the suite onto `<database>_test`, creating it if needed.

    The suite drops and truncates tables wholesale. Pointed at the development
    database that wipes the data you were working with, which is exactly what
    happened before this existed. The dev database and the test database must be
    different databases, not merely different rows.
    """
    configured = os.environ.get("CS_DATABASE_URL") or app.config.DEFAULT_DATABASE_URL
    url = make_url(configured)
    test_url = url.set(database=f"{url.database}_test")

    # CREATE DATABASE cannot run inside a transaction, hence AUTOCOMMIT.
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": test_url.database},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{test_url.database}"'))
    admin.dispose()

    os.environ["CS_DATABASE_URL"] = test_url.render_as_string(hide_password=False)
    # settings is built at import time, so rebuild it before anything reads it.
    importlib.reload(app.config)


_use_a_separate_test_database()

from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit  # noqa: E402
from app.db import Base, engine  # noqa: E402
from main import app as fastapi_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def schema():
    """Build the schema once for the whole run.

    Tests use create_all rather than `alembic upgrade head` so a broken migration
    cannot mask a broken model, and so the suite does not depend on migration
    ordering. `test_migrations_match_models` is what keeps the two in step.
    """
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def fresh_db(schema):
    # Truncate rather than drop/create per test: on Postgres the DDL round-trip
    # dominates the runtime of a suite this size. RESTART IDENTITY keeps generated
    # ids predictable across tests, CASCADE handles the foreign keys.
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    ratelimit.reset()
    yield


@pytest.fixture
def client():
    with TestClient(fastapi_app) as c:
        yield c


@pytest.fixture
def upload_dir() -> Path:
    return Path(_TMP) / "uploads"


def register(client: TestClient, name: str, password: str = "correct-horse-battery") -> None:
    """Register `name` with a matching address, so tests can talk about people by name."""
    response = client.post(
        "/signup",
        data={"email": f"{name}@example.com", "password": password, "display_name": name},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text


def csrf_for(client: TestClient) -> str:
    """Pull the CSRF token the server rendered into a form."""
    page = client.get("/listings/new")
    marker = 'name="csrf_token" value="'
    start = page.text.index(marker) + len(marker)
    return page.text[start : page.text.index('"', start)]

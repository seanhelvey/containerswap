import os
import tempfile
from pathlib import Path

import pytest

# Point the app at a throwaway data directory before anything imports settings.
_TMP = tempfile.mkdtemp(prefix="containerswap-tests-")
os.environ["CS_DATA_DIR"] = _TMP
os.environ["CS_SECRET_KEY"] = "test-secret-key-not-used-in-production"
os.environ["CS_DEBUG"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit  # noqa: E402
from app.db import Base, engine  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ratelimit.reset()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
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

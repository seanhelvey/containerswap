import socket
import threading
import time

import httpx
import pytest
import uvicorn

from main import app as fastapi_app


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server_url():
    """A real uvicorn instance serving the actual app, for tests that drive a real
    browser rather than TestClient. Runs in this process so it shares the same
    SQLAlchemy engine tests/conftest.py already pointed at containerswap_test."""
    port = _free_port()
    config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            if httpx.get(f"{base_url}/healthz", timeout=1).status_code == 200:
                break
        except httpx.TransportError:
            pass
        time.sleep(0.1)
    else:
        raise RuntimeError("live server did not come up in time")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from fastapi import FastAPI

from fopost_fastapi import FoPostSettings, install_exception_handlers, setup_fopost

BASE_URL = "https://api.test.fopost.com/api/v1"
API_KEY = "fp_test_key"
WEBHOOK_SECRET = "whsec_test"

Responder = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def settings() -> FoPostSettings:
    return FoPostSettings(
        api_key=API_KEY,
        base_url=BASE_URL,
        webhook_secret=WEBHOOK_SECRET,
        default_workspace_id="ws_1",
        _env_file=None,
    )


def stub_client(responder: Responder) -> httpx.Client:
    """An httpx client whose transport answers in-process. Never hits the network."""
    return httpx.Client(transport=httpx.MockTransport(responder))


@pytest.fixture
def make_app(settings: FoPostSettings) -> Callable[..., FastAPI]:
    def build(responder: Responder | None = None) -> FastAPI:
        app = FastAPI()
        setup_fopost(app, settings, http_client=stub_client(responder) if responder else None)
        install_exception_handlers(app)
        return app

    return build


@pytest.fixture(autouse=True)
def no_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record the SDK's retry waits instead of serving them, so the suite stays fast."""
    slept: list[float] = []
    monkeypatch.setattr("fopost._http._sleep", slept.append)
    return slept

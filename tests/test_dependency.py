from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fopost import Fopost

from fopost_fastapi import FoPostDep, fopost_lifespan, get_client

from .conftest import API_KEY, BASE_URL, stub_client


def _workspaces(request: httpx.Request) -> httpx.Response:
    assert request.headers["X-API-Key"] == API_KEY
    return httpx.Response(200, json={"data": [{"id": "ws_1", "name": "Acme", "slug": "acme"}]})


def test_dependency_injects_a_configured_client(make_app: Callable[..., FastAPI]) -> None:
    app = make_app(_workspaces)

    @app.get("/who")
    def who(fopost: FoPostDep) -> dict[str, object]:
        return {
            "type": type(fopost).__name__,
            "base_url": fopost.base_url,
            "workspaces": [w.name for w in fopost.workspaces.list()],
        }

    with TestClient(app) as client:
        body = client.get("/who").json()

    assert body == {"type": "Fopost", "base_url": BASE_URL, "workspaces": ["Acme"]}


def test_client_is_built_once_and_reused(make_app: Callable[..., FastAPI]) -> None:
    app = make_app(_workspaces)

    @app.get("/id")
    def identity(fopost: FoPostDep) -> dict[str, int]:
        return {"id": id(fopost)}

    with TestClient(app) as client:
        first = client.get("/id").json()["id"]
        second = client.get("/id").json()["id"]
        assert first == second == id(app.state.fopost)


def test_client_is_closed_on_shutdown(make_app: Callable[..., FastAPI]) -> None:
    app = make_app(_workspaces)

    @app.get("/ping")
    def ping(fopost: FoPostDep) -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        client.get("/ping")
        assert isinstance(app.state.fopost, Fopost)

    assert app.state.fopost is None


def test_lifespan_helper_wires_the_same_client() -> None:
    from fopost_fastapi import FoPostSettings

    settings = FoPostSettings(api_key=API_KEY, base_url=BASE_URL, _env_file=None)
    app = FastAPI(lifespan=fopost_lifespan(settings, http_client=stub_client(_workspaces)))

    @app.get("/base")
    def base(fopost: FoPostDep) -> dict[str, str]:
        return {"base_url": fopost.base_url}

    with TestClient(app) as client:
        assert client.get("/base").json() == {"base_url": BASE_URL}


def test_get_client_without_setup_is_a_clear_error() -> None:
    app = FastAPI()

    @app.get("/boom")
    def boom(fopost: FoPostDep) -> None:  # pragma: no cover - never reaches the body
        return None

    with (
        TestClient(app, raise_server_exceptions=True) as client,
        pytest.raises(RuntimeError) as err,
    ):
        client.get("/boom")

    assert "setup_fopost" in str(err.value)


def test_get_client_is_the_dependency_behind_the_alias() -> None:
    assert FoPostDep.__metadata__[0].dependency is get_client

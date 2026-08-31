from __future__ import annotations

from collections.abc import Callable

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fopost_fastapi import FoPostDep


def _responder(status: int, body: dict[str, object], headers: dict[str, str] | None = None):
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body, headers=headers)

    return respond


def _app_calling_the_api(make_app: Callable[..., FastAPI], responder) -> FastAPI:
    app = make_app(responder)

    @app.get("/labels")
    def labels(fopost: FoPostDep) -> object:
        return fopost.labels.list()

    return app


def test_a_rate_limit_becomes_a_429_with_retry_after(make_app: Callable[..., FastAPI]) -> None:
    app = _app_calling_the_api(
        make_app,
        _responder(
            429,
            {"error": "rate_limited", "message": "Too many requests"},
            {"Retry-After": "7"},
        ),
    )

    with TestClient(app) as client:
        response = client.get("/labels")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "7"
    assert response.json() == {"error": "rate_limited", "message": "Too many requests"}


def test_payment_required_keeps_the_upgrade_url(make_app: Callable[..., FastAPI]) -> None:
    app = _app_calling_the_api(
        make_app,
        _responder(
            402,
            {
                "error": "subscription_required",
                "message": "No active subscription",
                "upgrade_url": "https://fopost.com/dashboard/billing",
            },
        ),
    )

    with TestClient(app) as client:
        response = client.get("/labels")

    assert response.status_code == 402
    assert response.json()["upgrade_url"] == "https://fopost.com/dashboard/billing"


def test_not_found_passes_the_status_through(make_app: Callable[..., FastAPI]) -> None:
    app = _app_calling_the_api(
        make_app, _responder(404, {"error": "not_found", "message": "Label not found"})
    )

    with TestClient(app) as client:
        response = client.get("/labels")

    assert response.status_code == 404
    assert response.json() == {"error": "not_found", "message": "Label not found"}


def test_an_upstream_failure_becomes_a_gateway_error(make_app: Callable[..., FastAPI]) -> None:
    app = _app_calling_the_api(
        make_app, _responder(503, {"error": "unavailable", "message": "Try later"})
    )

    with TestClient(app) as client:
        response = client.get("/labels")

    assert response.status_code == 502
    assert response.json()["error"] == "unavailable"

from __future__ import annotations

import json
from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fopost_fastapi import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    FoPostWebhookRouter,
    WebhookEvent,
    sign_payload,
    verify_webhook_signature,
)

from .conftest import WEBHOOK_SECRET

PAYLOAD = {
    "event": "post.published",
    "data": {"id": "post_1", "workspace_id": "ws_1"},
    "timestamp": "2026-08-30T10:00:00.000Z",
}


def _body(payload: dict[str, object] | None = None) -> bytes:
    return json.dumps(payload if payload is not None else PAYLOAD).encode()


def _headers(
    body: bytes, *, secret: str = WEBHOOK_SECRET, event: str = "post.published"
) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: sign_payload(body, secret),
        EVENT_HEADER: event,
        DELIVERY_HEADER: "wh_1",
    }


def test_a_good_signature_is_accepted_and_the_handler_runs(
    make_app: Callable[..., FastAPI],
) -> None:
    seen: list[WebhookEvent] = []
    router = FoPostWebhookRouter()

    @router.on_event("post.published")
    async def published(event: WebhookEvent) -> None:
        seen.append(event)

    @router.on_event("post.failed")
    def never(event: WebhookEvent) -> None:  # pragma: no cover - must not run
        raise AssertionError("wrong handler ran")

    app = make_app()
    app.include_router(router, prefix="/fopost")

    body = _body()
    with TestClient(app) as client:
        response = client.post("/fopost/webhooks", content=body, headers=_headers(body))

    assert response.status_code == 200
    assert response.json() == {"received": True, "event": "post.published", "handlers": 1}
    assert len(seen) == 1
    assert seen[0].event == "post.published"
    assert seen[0].data == {"id": "post_1", "workspace_id": "ws_1"}
    assert seen[0].delivery_id == "wh_1"


def test_a_bad_signature_is_rejected_and_no_handler_runs(
    make_app: Callable[..., FastAPI],
) -> None:
    ran: list[str] = []
    router = FoPostWebhookRouter()

    @router.on_event("post.published")
    def published(event: WebhookEvent) -> None:  # pragma: no cover - must not run
        ran.append(event.event)

    app = make_app()
    app.include_router(router, prefix="/fopost")

    body = _body()
    headers = _headers(body, secret="whsec_wrong")
    with TestClient(app) as client:
        response = client.post("/fopost/webhooks", content=body, headers=headers)

    assert response.status_code == 401
    assert ran == []


def test_a_missing_signature_header_is_rejected(make_app: Callable[..., FastAPI]) -> None:
    app = make_app()
    app.include_router(FoPostWebhookRouter(), prefix="/fopost")

    body = _body()
    with TestClient(app) as client:
        response = client.post(
            "/fopost/webhooks", content=body, headers={"Content-Type": "application/json"}
        )

    assert response.status_code == 401


def test_a_tampered_body_no_longer_matches(make_app: Callable[..., FastAPI]) -> None:
    app = make_app()
    app.include_router(FoPostWebhookRouter(), prefix="/fopost")

    signed = _body()
    tampered = _body({**PAYLOAD, "data": {"id": "post_evil"}})
    with TestClient(app) as client:
        response = client.post("/fopost/webhooks", content=tampered, headers=_headers(signed))

    assert response.status_code == 401


def test_a_wildcard_handler_sees_every_event(make_app: Callable[..., FastAPI]) -> None:
    seen: list[str] = []
    router = FoPostWebhookRouter()

    @router.on_event()
    def every(event: WebhookEvent) -> None:
        seen.append(event.event)

    app = make_app()
    app.include_router(router, prefix="/fopost")

    with TestClient(app) as client:
        for name in ("post.published", "delivery.failed"):
            payload = {**PAYLOAD, "event": name}
            body = _body(payload)
            response = client.post(
                "/fopost/webhooks", content=body, headers=_headers(body, event=name)
            )
            assert response.status_code == 200

    assert seen == ["post.published", "delivery.failed"]


def test_no_secret_anywhere_refuses_rather_than_trusting(settings_free_app: FastAPI) -> None:
    body = _body()
    with TestClient(settings_free_app) as client:
        response = client.post(
            "/fopost/webhooks",
            content=body,
            headers=_headers(body),
            # A 500 here is the point: never accept unverifiable traffic.
        )

    assert response.status_code == 500


@pytest.fixture
def settings_free_app() -> FastAPI:
    app = FastAPI()
    app.include_router(FoPostWebhookRouter(), prefix="/fopost")
    return app


def test_a_router_level_secret_overrides_settings(make_app: Callable[..., FastAPI]) -> None:
    app = make_app()
    app.include_router(FoPostWebhookRouter(secret="whsec_router"), prefix="/fopost")

    body = _body()
    with TestClient(app) as client:
        assert (
            client.post("/fopost/webhooks", content=body, headers=_headers(body)).status_code == 401
        )
        assert (
            client.post(
                "/fopost/webhooks", content=body, headers=_headers(body, secret="whsec_router")
            ).status_code
            == 200
        )


def test_signature_helpers_round_trip() -> None:
    body = b'{"event":"post.published"}'
    header = sign_payload(body, WEBHOOK_SECRET)

    assert header.startswith("sha256=")
    assert verify_webhook_signature(body, header, WEBHOOK_SECRET) is True
    assert verify_webhook_signature(body, header, "other") is False
    assert verify_webhook_signature(body, None, WEBHOOK_SECRET) is False
    assert verify_webhook_signature(b"{}", header, WEBHOOK_SECRET) is False

"""Receive FoPost webhooks.

FoPost signs every delivery with HMAC-SHA256 over the **raw** request body,
using that webhook's secret, and sends it as::

    X-FoPost-Signature: sha256=<hex digest>
    X-FoPost-Event: post.published
    X-FoPost-Delivery: <delivery id>

The body is ``{"event": ..., "data": {...}, "timestamp": "<ISO 8601>"}``.
The signature covers the bytes as sent, so it is verified before any parsing —
re-serialising the JSON would change the digest.
"""

from __future__ import annotations

import hmac
import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable
from hashlib import sha256
from typing import Any, TypeVar, cast

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from .concurrency import run_fopost
from .settings import FoPostSettings

__all__ = [
    "ANY_EVENT",
    "DELIVERY_HEADER",
    "EVENT_HEADER",
    "SIGNATURE_HEADER",
    "WEBHOOK_EVENTS",
    "FoPostWebhookRouter",
    "WebhookEvent",
    "on_event",
    "sign_payload",
    "verify_webhook_signature",
    "webhook_router",
]

SIGNATURE_HEADER = "X-FoPost-Signature"
EVENT_HEADER = "X-FoPost-Event"
DELIVERY_HEADER = "X-FoPost-Delivery"
_SIGNATURE_PREFIX = "sha256="

#: Subscribe to every event, whatever it is.
ANY_EVENT = "*"

#: Events FoPost can deliver, as accepted by ``POST /v1/webhooks``.
WEBHOOK_EVENTS = (
    "post.published",
    "post.failed",
    "post.partially_failed",
    "delivery.published",
    "delivery.failed",
    "delivery.delayed",
    "account.health_changed",
)


class WebhookEvent(BaseModel):
    """One delivery, as FoPost sends it."""

    event: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: str | None = None
    delivery_id: str | None = Field(
        default=None,
        description="Value of the X-FoPost-Delivery header, not part of the body.",
    )


Handler = Callable[[WebhookEvent], Awaitable[None] | None]
H = TypeVar("H", bound=Handler)


def sign_payload(body: bytes, secret: str) -> str:
    """Return the header value FoPost sends for ``body``, ``sha256=`` included."""
    digest = hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()
    return f"{_SIGNATURE_PREFIX}{digest}"


def verify_webhook_signature(body: bytes, header: str | None, secret: str) -> bool:
    """Constant-time check of a delivery signature against the raw body."""
    if not header or not secret:
        return False
    return hmac.compare_digest(sign_payload(body, secret), header.strip())


class FoPostWebhookRouter(APIRouter):
    """An ``APIRouter`` that verifies FoPost signatures and fans out to handlers.

    ::

        app.include_router(webhook_router, prefix="/fopost")

        @on_event("post.published")
        async def published(event: WebhookEvent) -> None:
            ...

    The secret comes from ``FoPostSettings.webhook_secret`` (``FOPOST_WEBHOOK_SECRET``)
    unless one is passed here. With no secret at all the route answers 500 rather
    than accepting unverified traffic.
    """

    def __init__(
        self,
        *,
        path: str = "/webhooks",
        secret: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._handlers: defaultdict[str, list[Handler]] = defaultdict(list)
        self._secret = secret
        self.add_api_route(
            path,
            self._receive,
            methods=["POST"],
            name="fopost_webhook",
            summary="Receive a FoPost webhook",
            include_in_schema=False,
        )

    def on_event(self, event: str = ANY_EVENT) -> Callable[[H], H]:
        """Register a handler for one event, or for :data:`ANY_EVENT`."""

        def decorator(func: H) -> H:
            self._handlers[event].append(func)
            return func

        return decorator

    def handlers_for(self, event: str) -> list[Handler]:
        return [*self._handlers.get(event, ()), *self._handlers.get(ANY_EVENT, ())]

    def _resolve_secret(self, request: Request) -> str | None:
        if self._secret:
            return self._secret
        settings = getattr(request.app.state, "fopost_settings", None)
        if isinstance(settings, FoPostSettings):
            return settings.webhook_secret
        return None

    async def _receive(self, request: Request) -> dict[str, Any]:
        secret = self._resolve_secret(request)
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="fopost webhook secret is not configured",
            )

        # Read the raw bytes first — the signature covers them exactly.
        body = await request.body()
        if not verify_webhook_signature(body, request.headers.get(SIGNATURE_HEADER), secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid fopost webhook signature",
            )

        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="fopost webhook body is not valid JSON",
            ) from exc
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="fopost webhook body is not an object",
            )

        payload.setdefault("event", request.headers.get(EVENT_HEADER, ""))
        payload["delivery_id"] = request.headers.get(DELIVERY_HEADER) or None
        event = WebhookEvent.model_validate(payload)

        handled = await self._dispatch(event)
        return {"received": True, "event": event.event, "handlers": handled}

    async def _dispatch(self, event: WebhookEvent) -> int:
        """Run every handler for the event. Blocking handlers go to a worker thread."""
        handlers = self.handlers_for(event.event)
        for handler in handlers:
            if inspect.iscoroutinefunction(handler):
                await handler(event)
            else:
                await run_fopost(cast(Callable[[WebhookEvent], None], handler), event)
        return len(handlers)


#: The router most apps include, and the decorator that feeds it.
webhook_router = FoPostWebhookRouter()
on_event = webhook_router.on_event

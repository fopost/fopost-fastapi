"""Turn ``fopost`` SDK exceptions into HTTP responses.

An unhandled SDK error is a 500 with a stack trace. Registering the handler
below turns it into the status the FoPost API actually answered with, keeping
the machine-readable ``error`` code, the 402 ``upgrade_url``, and the 429
``Retry-After`` intact so the caller can act on them.
"""

from __future__ import annotations

import math
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fopost import FopostError, PaymentRequiredError, RateLimitError

__all__ = ["fopost_exception_handler", "install_exception_handlers"]

#: Upstream 5xx becomes a gateway error — this app is fine, its dependency is not.
_UPSTREAM_FAILURE_STATUS = 502


def _status_for(exc: FopostError) -> int:
    if 400 <= exc.status < 500:
        return exc.status
    return _UPSTREAM_FAILURE_STATUS


def _retry_after_header(exc: RateLimitError) -> dict[str, str]:
    if exc.retry_after is None:
        return {}
    return {"Retry-After": str(max(0, math.ceil(exc.retry_after)))}


async def fopost_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render a ``FopostError`` as JSON, preserving what the caller needs."""
    if not isinstance(exc, FopostError):  # pragma: no cover - registered by type
        raise exc

    payload: dict[str, Any] = {
        "error": exc.code or "fopost_error",
        "message": exc.message,
    }
    headers: dict[str, str] = {}

    if isinstance(exc, PaymentRequiredError) and exc.upgrade_url:
        payload["upgrade_url"] = exc.upgrade_url
    if isinstance(exc, RateLimitError):
        headers = _retry_after_header(exc)

    return JSONResponse(payload, status_code=_status_for(exc), headers=headers or None)


def install_exception_handlers(app: FastAPI) -> None:
    """Register :func:`fopost_exception_handler` for every SDK error."""
    app.add_exception_handler(FopostError, fopost_exception_handler)

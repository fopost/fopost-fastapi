"""fopost-fastapi — the official FastAPI integration for the FoPost API.

A thin wrapper: every request, model, retry, and error type lives in the
``fopost`` package. This one wires that client into FastAPI's idioms —
settings, dependency injection, a webhook receiver, and an exception handler.

::

    from fastapi import FastAPI
    from fopost_fastapi import FoPostDep, install_exception_handlers, setup_fopost

    app = FastAPI()
    setup_fopost(app)
    install_exception_handlers(app)

    @app.get("/workspaces")
    def workspaces(fopost: FoPostDep):
        return fopost.workspaces.list()

``fopost`` is synchronous. A ``def`` route like the one above is already run in
a worker thread by FastAPI; from an ``async def`` route, wrap the call in
:func:`run_fopost` so the event loop keeps turning.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from .client import (
    STATE_ATTR,
    FoPostDep,
    FoPostSettingsDep,
    create_client,
    fopost_lifespan,
    get_client,
    get_settings,
    setup_fopost,
)
from .concurrency import run_fopost
from .errors import fopost_exception_handler, install_exception_handlers
from .settings import FoPostSettings
from .webhooks import (
    ANY_EVENT,
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    WEBHOOK_EVENTS,
    FoPostWebhookRouter,
    WebhookEvent,
    on_event,
    sign_payload,
    verify_webhook_signature,
    webhook_router,
)

try:
    __version__ = _pkg_version("fopost-fastapi")
except PackageNotFoundError:  # running from a source tree
    __version__ = "0.0.0"

__all__ = [
    "ANY_EVENT",
    "DELIVERY_HEADER",
    "EVENT_HEADER",
    "SIGNATURE_HEADER",
    "STATE_ATTR",
    "WEBHOOK_EVENTS",
    "FoPostDep",
    "FoPostSettings",
    "FoPostSettingsDep",
    "FoPostWebhookRouter",
    "WebhookEvent",
    "__version__",
    "create_client",
    "fopost_exception_handler",
    "fopost_lifespan",
    "get_client",
    "get_settings",
    "install_exception_handlers",
    "on_event",
    "run_fopost",
    "setup_fopost",
    "sign_payload",
    "verify_webhook_signature",
    "webhook_router",
]

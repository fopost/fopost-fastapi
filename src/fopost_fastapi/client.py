"""Client construction, app wiring, and the injectable dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, Request
from fopost import Fopost

from .concurrency import run_fopost
from .settings import FoPostSettings

__all__ = [
    "STATE_ATTR",
    "FoPostDep",
    "FoPostSettingsDep",
    "create_client",
    "fopost_lifespan",
    "get_client",
    "get_settings",
    "setup_fopost",
]

#: Attribute on ``app.state`` holding the one client the app shares.
STATE_ATTR = "fopost"
_SETTINGS_ATTR = "fopost_settings"


def create_client(
    settings: FoPostSettings | None = None,
    *,
    http_client: httpx.Client | None = None,
) -> Fopost:
    """Build a ``Fopost`` client from settings.

    ``http_client`` is an injection point for tests: pass an ``httpx.Client``
    carrying a mock transport and no request ever leaves the process.
    """
    settings = settings or FoPostSettings()
    if not settings.api_key:
        raise RuntimeError(
            "fopost-fastapi: no API key — set FOPOST_API_KEY or pass "
            "FoPostSettings(api_key=...) to setup_fopost()"
        )
    return Fopost(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=settings.timeout,
        max_retries=settings.max_retries,
        http_client=http_client,
    )


def setup_fopost(
    app: FastAPI,
    settings: FoPostSettings | None = None,
    *,
    http_client: httpx.Client | None = None,
) -> FoPostSettings:
    """Wire FoPost into ``app``: one client for the whole process.

    Call this at import time, before the app starts serving::

        app = FastAPI()
        setup_fopost(app)

    The client is created when the app starts and closed when it stops, and it
    wraps whatever lifespan the app already has rather than replacing it.
    Returns the resolved settings so routers can read ``webhook_secret`` and
    ``default_workspace_id`` from them.
    """
    settings = settings or FoPostSettings()
    setattr(app.state, _SETTINGS_ATTR, settings)

    inner = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[Any]:
        client = create_client(settings, http_client=http_client)
        setattr(app.state, STATE_ATTR, client)
        try:
            async with inner(app) as state:
                yield state
        finally:
            setattr(app.state, STATE_ATTR, None)
            await run_fopost(client.close)

    app.router.lifespan_context = lifespan
    return settings


def fopost_lifespan(
    settings: FoPostSettings | None = None,
    *,
    http_client: httpx.Client | None = None,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """A lifespan to hand straight to ``FastAPI(lifespan=...)``.

    ::

        app = FastAPI(lifespan=fopost_lifespan())

    Equivalent to :func:`setup_fopost` for an app with no lifespan of its own.
    """
    resolved = settings or FoPostSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        setattr(app.state, _SETTINGS_ATTR, resolved)
        client = create_client(resolved, http_client=http_client)
        setattr(app.state, STATE_ATTR, client)
        try:
            yield
        finally:
            setattr(app.state, STATE_ATTR, None)
            await run_fopost(client.close)

    return lifespan


def get_client(request: Request) -> Fopost:
    """Dependency returning the shared client. Never builds one per request."""
    client = getattr(request.app.state, STATE_ATTR, None)
    if not isinstance(client, Fopost):
        raise RuntimeError(
            "fopost-fastapi: no client on app.state — call setup_fopost(app) or pass "
            "lifespan=fopost_lifespan() when creating the app"
        )
    return client


def get_settings(request: Request) -> FoPostSettings:
    """Dependency returning the settings the app was wired with."""
    settings = getattr(request.app.state, _SETTINGS_ATTR, None)
    if settings is None:
        raise RuntimeError(
            "fopost-fastapi: no settings on app.state — call setup_fopost(app) or pass "
            "lifespan=fopost_lifespan() when creating the app"
        )
    if not isinstance(settings, FoPostSettings):  # pragma: no cover - defensive
        raise RuntimeError("fopost-fastapi: app.state.fopost_settings is not FoPostSettings")
    return settings


#: Inject the shared client: ``def route(fopost: FoPostDep) -> ...``
FoPostDep = Annotated[Fopost, Depends(get_client)]

#: Inject the resolved settings: ``def route(settings: FoPostSettingsDep) -> ...``
FoPostSettingsDep = Annotated[FoPostSettings, Depends(get_settings)]

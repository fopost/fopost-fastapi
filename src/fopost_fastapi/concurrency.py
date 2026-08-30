"""Bridge between the synchronous ``fopost`` SDK and the event loop.

The ``fopost`` package ships a blocking client only — there is no async variant —
so every call made from an ``async def`` route has to leave the event loop.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from fastapi.concurrency import run_in_threadpool

__all__ = ["run_fopost"]

P = ParamSpec("P")
R = TypeVar("R")


async def run_fopost(
    func: Callable[P, R],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    """Await a blocking FoPost call without stalling the event loop.

    ::

        @app.post("/posts")
        async def create(fopost: FoPostDep):
            return await run_fopost(
                fopost.posts.create,
                workspace_id="9b2f6c1e-...",
                content="Hello from FastAPI",
                accounts=[...],
            )

    A plain ``def`` route needs none of this — FastAPI already runs those in a
    worker thread, so call the SDK directly there.
    """
    return await run_in_threadpool(functools.partial(func, *args, **kwargs))

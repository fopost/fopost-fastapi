"""Receive published blog articles from the FoPost Website target.

A post goes to a social network; an article goes to a website. When FoPost
publishes an article to a Website target it sends the article to your URL,
signed with the website secret shown once in the blog settings. Signature
checking lives in the ``fopost`` SDK (``fopost.webhooks.verify``); this module
only shapes it as an ``APIRouter`` and hands the typed payload to your callback.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request, status
from fopost import ArticlePublishedPayload, WebhookVerificationError, webhooks

from .concurrency import run_fopost

__all__ = ["ArticleCallback", "article_router"]

ArticleCallback = Callable[[ArticlePublishedPayload], Awaitable[str | None] | str | None]

_PUBLISHED_EVENT = "article.published"


def article_router(
    secret: str,
    on_article_published: ArticleCallback,
    *,
    path: str = "/articles",
    tolerance: float = webhooks.SIGNATURE_TOLERANCE_SECONDS,
    **kwargs: Any,
) -> APIRouter:
    """Build the router a Website target posts to.

    ::

        app.include_router(article_router(secret=WEBSITE_SECRET, on_article_published=store))

    A bad or stale signature answers 401 and the callback never runs. An
    ``article.test`` delivery answers ``{"ok": true}``. An ``article.published``
    delivery reaches ``on_article_published`` as an ``ArticlePublishedPayload``;
    the callback may be sync or async, and a URL string it returns is echoed as
    ``{"url": ...}``. Any other event answers ``{"ok": true}`` and is ignored.
    """
    if not secret:
        raise ValueError("article_router needs the website secret")

    router = APIRouter(**kwargs)

    async def receive(request: Request) -> dict[str, Any]:
        # The signature covers the bytes as sent, so read them before any parsing.
        body = await request.body()
        try:
            event = webhooks.verify(body, request.headers, secret, tolerance=tolerance)
        except WebhookVerificationError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.code) from exc

        # article.test, and anything else, is acknowledged and ignored.
        if event.event != _PUBLISHED_EVENT:
            return {"ok": True}

        article = ArticlePublishedPayload.model_validate(event.data)
        if inspect.iscoroutinefunction(on_article_published):
            result = await on_article_published(article)
        else:
            sync = cast(Callable[[ArticlePublishedPayload], "str | None"], on_article_published)
            result = await run_fopost(sync, article)
        return {"url": result} if isinstance(result, str) else {"ok": True}

    router.add_api_route(
        path,
        receive,
        methods=["POST"],
        name="fopost_article",
        summary="Receive a published FoPost article",
        include_in_schema=False,
    )
    return router

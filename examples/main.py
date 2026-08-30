"""A runnable FastAPI app: create a post, publish it, and receive the webhook.

    pip install fopost-fastapi uvicorn
    export FOPOST_API_KEY=fp_...
    export FOPOST_DEFAULT_WORKSPACE_ID=9b2f6c1e-...
    export FOPOST_WEBHOOK_SECRET=...          # the secret of your FoPost webhook
    uvicorn examples.main:app --reload

Then point a FoPost webhook at ``https://<your host>/fopost/webhooks``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from fopost_fastapi import (
    FoPostDep,
    FoPostSettingsDep,
    WebhookEvent,
    install_exception_handlers,
    on_event,
    run_fopost,
    setup_fopost,
    webhook_router,
)

log = logging.getLogger("example")

app = FastAPI(title="FoPost example")
setup_fopost(app)
install_exception_handlers(app)
app.include_router(webhook_router, prefix="/fopost")


class NewPost(BaseModel):
    text: str
    accounts: list[str]
    publish: bool = False


@app.get("/accounts")
def list_accounts(fopost: FoPostDep, settings: FoPostSettingsDep) -> list[dict[str, Any]]:
    """A ``def`` route: FastAPI already runs it in a worker thread, so call the SDK directly."""
    if not settings.default_workspace_id:
        raise HTTPException(400, "set FOPOST_DEFAULT_WORKSPACE_ID")
    accounts = fopost.accounts.list(workspace_id=settings.default_workspace_id)
    return [{"id": a.id, "platform": a.platform, "username": a.username} for a in accounts]


@app.post("/posts")
async def create_post(
    body: NewPost, fopost: FoPostDep, settings: FoPostSettingsDep
) -> dict[str, Any]:
    """An ``async def`` route: the blocking SDK goes through ``run_fopost``."""
    if not settings.default_workspace_id:
        raise HTTPException(400, "set FOPOST_DEFAULT_WORKSPACE_ID")

    post = await run_fopost(
        fopost.posts.create,
        workspace_id=settings.default_workspace_id,
        content=body.text,
        accounts=body.accounts,
    )
    if body.publish:
        # Returns once delivery is queued, not once the post is live.
        await run_fopost(fopost.posts.publish, post.id)

    return {"id": post.id, "status": post.status}


@on_event("post.published")
async def post_published(event: WebhookEvent) -> None:
    log.info("published: %s", event.data.get("id"))


@on_event("post.failed")
async def post_failed(event: WebhookEvent) -> None:
    log.warning("failed: %s", event.data)

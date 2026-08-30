# fopost-fastapi

[![PyPI](https://img.shields.io/pypi/v/fopost-fastapi.svg)](https://pypi.org/project/fopost-fastapi/)
[![Python versions](https://img.shields.io/pypi/pyversions/fopost-fastapi.svg)](https://pypi.org/project/fopost-fastapi/)
[![CI](https://github.com/fopost/fopost-fastapi/actions/workflows/ci.yml/badge.svg)](https://github.com/fopost/fopost-fastapi/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Official FastAPI integration for the [FoPost](https://fopost.com) API. Schedule and publish to
+30 social platforms from your code.

This is a **thin wrapper**. Every request, model, retry, and error type lives in the
[`fopost`](https://pypi.org/project/fopost/) SDK — this package wires that client into FastAPI's
idioms: settings, dependency injection, a webhook receiver, and an exception handler.

```bash
pip install fopost-fastapi
```

Requires Python 3.10 or newer, FastAPI 0.110 or newer, and pydantic v2.

> **0.x release.** The public API is still settling and minor versions may contain breaking
> changes. Pin an exact version if that matters to you.

## Quick start

```python
from fastapi import FastAPI

from fopost_fastapi import FoPostDep, install_exception_handlers, setup_fopost

app = FastAPI()
setup_fopost(app)              # one client, created at startup, closed at shutdown
install_exception_handlers(app)


@app.get("/workspaces")
def workspaces(fopost: FoPostDep):
    return fopost.workspaces.list()
```

`FoPostDep` is `Annotated[Fopost, Depends(get_client)]`. The client is built **once** when the
app starts and shared by every request — the dependency looks it up, it never constructs one.

If your app already has its own lifespan, `setup_fopost` wraps it rather than replacing it.
To wire FoPost through the lifespan directly instead:

```python
from fopost_fastapi import fopost_lifespan

app = FastAPI(lifespan=fopost_lifespan())
```

## Settings

`FoPostSettings` is a `pydantic-settings` model reading `FOPOST_`-prefixed environment variables
(and a `.env` file, if present).

| Field | Environment variable | Default |
| :--- | :--- | :--- |
| `api_key` | `FOPOST_API_KEY` | — (required) |
| `base_url` | `FOPOST_BASE_URL` | `https://api.fopost.com/api/v1` |
| `timeout` | `FOPOST_TIMEOUT` | `30.0` seconds |
| `max_retries` | `FOPOST_MAX_RETRIES` | `3` attempts |
| `default_workspace_id` | `FOPOST_DEFAULT_WORKSPACE_ID` | — |
| `webhook_secret` | `FOPOST_WEBHOOK_SECRET` | — |

Create an API key at <https://app.fopost.com/api-keys>. It is sent as `X-API-Key`.

Pass settings explicitly when you would rather not read the environment:

```python
setup_fopost(app, FoPostSettings(api_key="fp_...", base_url="https://api.fopost.com/api/v1"))
```

`FoPostSettingsDep` injects the resolved settings into a route, which is how you reach
`default_workspace_id`.

## Sync or async? The SDK is synchronous

The `fopost` package ships a **blocking** client only — there is no async variant, and this
package deliberately does not write one. That leaves two shapes:

```python
# A `def` route — FastAPI already runs it in a worker thread. Call the SDK directly.
@app.get("/accounts")
def accounts(fopost: FoPostDep, settings: FoPostSettingsDep):
    return fopost.accounts.list(workspace_id=settings.default_workspace_id)


# An `async def` route — the call must leave the event loop, or it stalls the server.
from fopost_fastapi import run_fopost

@app.post("/posts")
async def create(fopost: FoPostDep, settings: FoPostSettingsDep):
    return await run_fopost(
        fopost.posts.create,
        workspace_id=settings.default_workspace_id,
        content="Hello from FastAPI",
        accounts=["<account id>"],
    )
```

`run_fopost` is a thin wrapper over `fastapi.concurrency.run_in_threadpool`. Never call the SDK
straight from an `async def` route: a 30-second timeout would block every other request.

## Receiving webhooks

```python
from fopost_fastapi import WebhookEvent, on_event, webhook_router

app.include_router(webhook_router, prefix="/fopost")   # POST /fopost/webhooks


@on_event("post.published")
async def published(event: WebhookEvent) -> None:
    print(event.data["id"], event.timestamp)


@on_event("post.failed")
def failed(event: WebhookEvent) -> None:      # a `def` handler runs in a worker thread
    ...
```

Point a FoPost webhook at `https://<your host>/fopost/webhooks` and put its secret in
`FOPOST_WEBHOOK_SECRET`.

FoPost signs each delivery with HMAC-SHA256 over the **raw** request body using that webhook's
secret, and sends it as `X-FoPost-Signature: sha256=<hex>` alongside `X-FoPost-Event` and
`X-FoPost-Delivery`. The router reads the raw bytes before any parsing, compares with
`hmac.compare_digest`, and answers **401** on a mismatch or a missing header — no handler runs.
With no secret configured at all it answers 500 rather than accepting unverifiable traffic.

Events: `post.published`, `post.failed`, `post.partially_failed`, `delivery.published`,
`delivery.failed`, `delivery.delayed`, `account.health_changed`. `@on_event()` with no argument
subscribes to all of them.

Run several receivers, or keep the secret out of the environment, by building your own router:

```python
from fopost_fastapi import FoPostWebhookRouter

router = FoPostWebhookRouter(secret="whsec_...", path="/callbacks")
app.include_router(router, prefix="/fopost")
```

`sign_payload(body, secret)` and `verify_webhook_signature(body, header, secret)` are exported
if you need to verify a delivery somewhere else.

## Error handling

`install_exception_handlers(app)` turns an SDK exception into the status the FoPost API actually
answered with, instead of a 500 and a stack trace.

| SDK error | Response |
| :--- | :--- |
| `AuthenticationError` (401), `PermissionDeniedError` (403), `NotFoundError` (404) | the same status |
| `PaymentRequiredError` (402) | 402, body keeps `upgrade_url` |
| `RateLimitError` (429) | 429 with a `Retry-After` header |
| any 4xx | the same status |
| any 5xx or transport failure | 502 — your app is fine, its dependency is not |

The body is the API's own envelope: `{"error": "<machine code>", "message": "<human text>"}`.

Retries are the SDK's job, not this package's: a 429 is retried up to `max_retries` attempts,
honouring `Retry-After`, before the error ever reaches the handler.

## The rest of the API

Everything you can call on the injected client — `posts`, `accounts`, `workspaces`, `labels`,
`ai`, and the `request()` escape hatch for endpoints the SDK does not wrap — is documented in the
[`fopost` SDK](https://github.com/fopost/fopost-python). This package adds no resources of its own
and stores nothing.

## Example

[`examples/main.py`](examples/main.py) is a complete app: settings from the environment, the
injected client in both a `def` and an `async def` route, and the webhook receiver.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check . && ruff format --check .
mypy
```

The suite is fully offline — it stubs the SDK's HTTP transport and never reaches the network.

## Links

- Documentation — <https://fopost.com/docs>
- Python SDK — <https://github.com/fopost/fopost-python>
- Issues — <https://github.com/fopost/fopost-fastapi/issues>
- Support — <https://fopost.com/contact>

MIT licensed. Copyright (c) 2026 Porter Bridge, LLC.

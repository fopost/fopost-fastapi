# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## What This Is

`fopost-fastapi` on PyPI, imported as `fopost_fastapi`. The official FastAPI integration for the
FoPost API. It is a **thin wrapper** over the `fopost` package (PyPI, sibling repo
`fopost-python`) and adds no API surface of its own.

**This package never reimplements API logic.** No HTTP client, no endpoint wrappers, no models,
no retry loop, no error classes — all of that is `fopost`'s. What lives here is only the wiring:
pydantic settings, a shared client on `app.state`, a `Depends` alias, a signature-verifying
webhook router, and an exception handler. If a change would add a resource method or touch a
request, it belongs in `fopost-python` instead.

It also stores nothing: no database models, no ORM, no migrations.

## Brand Rules

- The product is **FoPost** (`fopost.com`). Never write "OwlStack" — retired Aug 2026.
- Never write an email address. Support is https://fopost.com/contact and GitHub issues.
- Never name AI providers/models, infrastructure vendors, or any person.

## Parent dependency

`fopost` is **published on PyPI**, so `pip install -e '.[dev]'` resolves it normally. No
CI-from-source shim is needed.

`pyproject.toml` declares `fopost>=0.1,<1.0`.

**Python floor.** The parent `fopost` requires Python **3.10+**, so this package declares
`requires-python = ">=3.10"` and the CI matrix runs 3.10–3.13. Declaring 3.9 would ship a package
pip cannot resolve on 3.9. Do not lower the floor unless `fopost` lowers its own first.

## The parent SDK is synchronous

`fopost` ships a blocking client (`Fopost`, built on `httpx.Client`). **There is no `AsyncFoPost`
and this package must not write one.** Do not add an async HTTP client, do not re-wrap `httpx`.

The consequence is baked into the design:

- A `def` route is already run in a worker thread by FastAPI — call the SDK directly there.
- An `async def` route must go through `run_fopost(...)` (`concurrency.py`, a wrapper over
  `fastapi.concurrency.run_in_threadpool`), or a 30-second request blocks the whole event loop.
- Client shutdown (`client.close()`) also goes through `run_fopost`, since it is blocking too.
- Blocking webhook handlers are dispatched through `run_fopost` for the same reason.

If `fopost` ever gains a native async client, that is the moment to add an async path here — not
before.

## Architecture

```
src/fopost_fastapi/
  __init__.py       re-exports the whole public API
  settings.py       FoPostSettings — pydantic-settings, env prefix FOPOST_
  client.py         create_client / setup_fopost / fopost_lifespan / get_client / FoPostDep
  concurrency.py    run_fopost — the threadpool bridge
  errors.py         fopost_exception_handler / install_exception_handlers
  webhooks.py       FoPostWebhookRouter, on_event, signature verification
```

**Client lifetime.** One `Fopost` per process, not per request. `setup_fopost(app)` wraps
`app.router.lifespan_context` so the client is created at startup, stored on
`app.state.fopost` (`STATE_ATTR`), and closed at shutdown — wrapping, so an app that already has
its own lifespan keeps it. `fopost_lifespan()` is the same thing shaped for
`FastAPI(lifespan=...)`. `get_client(request)` only *reads* `app.state`; it must never construct
a client, or connection pooling is lost.

`create_client(settings, http_client=...)` takes an `httpx.Client` purely so tests can inject a
mock transport. Production callers leave it unset.

## API Contract

The bits that matter here (the full contract is `fopost-python`'s):

- Base URL `https://api.fopost.com/api/v1`, auth header **`X-API-Key`** (not Bearer)
- Error envelope `{"error": "<machine code>", "message": "<human text>"}`; 402 may carry
  `upgrade_url`, 429 carries `Retry-After`
- Retries (3 attempts, honouring `Retry-After`) happen inside `fopost`. Never add a retry loop here

### Webhook signature scheme

Read off the API source (`fopost/apps/api/src/services/webhook-dispatcher.ts` `signPayload`, and
`apps/api/src/workers/webhook.worker.ts`), not guessed:

- `X-FoPost-Signature: sha256=<hex>` — `HMAC-SHA256(raw request body, webhook.secret)`, hex digest,
  prefixed with the literal `sha256=`. No timestamp is mixed in, so there is no replay window to
  enforce and none is implemented
- `X-FoPost-Event: <event name>`, `X-FoPost-Delivery: <delivery id>`
- Body: `{"event": "...", "data": {...}, "timestamp": "<ISO 8601>"}`
- Events: `post.published`, `post.failed`, `post.partially_failed`, `delivery.published`,
  `delivery.failed`, `delivery.delayed`, `account.health_changed`

**The signature covers the bytes as sent.** `_receive` reads `await request.body()` *before* any
parsing and compares with `hmac.compare_digest`. Never verify against re-serialised JSON — key
order and separators would change the digest. Mismatch or missing header is **401**; no secret
configured at all is **500**, never a silent accept.

If the API changes the scheme, this repo follows the API — re-read those two files rather than
inventing a variant.

## Commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check . && ruff format --check .
mypy
python -m build
```

Tests are **fully offline**: `tests/conftest.py` builds an `httpx.Client` over
`httpx.MockTransport`, and `no_retry_sleep` swaps out `fopost._http._sleep` so retry backoff does
not slow the suite. Never let a test reach the network.

## Conventions

- Formatted and linted with `ruff` (line length 100, `E,F,I,UP,B`), type-checked with strict
  `mypy`. Full type hints; `py.typed` ships in the wheel
- `from __future__ import annotations` at the top of every module
- Public symbols carry a docstring; obvious code does not get a narrated comment. A comment
  explains a non-obvious "why" in one line
- Every public name is re-exported from `__init__.py` and listed in its `__all__`

## Releasing

Tag `v<version>` matching `pyproject.toml` (e.g. `v0.1.0`); `.github/workflows/release.yml`
verifies the tag against the version, lints, tests, builds, smoke-tests the wheel, and publishes.

**No secret is required.** Publishing uses **PyPI trusted publishing** (OIDC), so the workflow
requests `id-token: write` and `pypa/gh-action-pypi-publish` exchanges it for a short-lived token.
Configure it once on PyPI before the first tag:

1. PyPI → the `fopost-fastapi` project → *Publishing* (for a first-ever release, use *Your
   projects → Publishing → Add a pending publisher*)
2. Add a **GitHub** publisher: owner `fopost`, repository `fopost-fastapi`, workflow filename
   `release.yml`, environment name `pypi`
3. In GitHub → Settings → Environments, create the `pypi` environment (add required reviewers if
   a release should need approval)

The `environment: pypi` block in the workflow must keep matching the publisher's environment name,
or PyPI rejects the token exchange.

## Git

Conventional Commits, atomic — one logical change per commit. Branch `feature/<description>`,
merge to `main` via PR. Never `gh pr create` — push the branch and hand over the compare link:
`https://github.com/fopost/fopost-fastapi/compare/main...<branch>`

# Example

`main.py` is a complete FastAPI app: settings from the environment, the injected client in
both a `def` and an `async def` route, and the webhook receiver.

```bash
pip install fopost-fastapi uvicorn
export FOPOST_API_KEY=fp_...
export FOPOST_DEFAULT_WORKSPACE_ID=9b2f6c1e-...
export FOPOST_WEBHOOK_SECRET=...
uvicorn examples.main:app --reload
```

```bash
curl localhost:8000/accounts
curl -X POST localhost:8000/posts \
  -H 'content-type: application/json' \
  -d '{"text": "Hello from FastAPI", "accounts": ["<account id>"], "publish": true}'
```

Create the webhook in FoPost (or with the SDK) pointing at `https://<your host>/fopost/webhooks`,
and put its secret in `FOPOST_WEBHOOK_SECRET`.

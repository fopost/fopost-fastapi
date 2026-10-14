# Changelog

## Unreleased

- `article_router(secret, on_article_published)`: receive `article.published` deliveries from a
  Website blog target, verified through `fopost.webhooks.verify`; 401 on a bad signature,
  `{"ok": true}` for `article.test`, a returned URL echoed as `{"url": ...}`.
- The parent floor is now `fopost>=0.3`, which carries `client.blog` and the webhook verifier.

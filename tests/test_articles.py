from __future__ import annotations

import hashlib
import hmac
import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fopost import ArticlePublishedPayload

from fopost_fastapi import ArticleCallback, article_router

SECRET = "whsec_site"

ARTICLE = {
    "id": "art_1",
    "title": "Best trail running shoes",
    "slug": "best-trail-running-shoes",
    "excerpt": None,
    "metaTitle": None,
    "metaDescription": None,
    "bodyMarkdown": "# Shoes",
    "bodyHtml": "<h1>Shoes</h1>",
    "featuredImage": {"mediaId": "med_1", "url": "https://cdn.example/a.jpg", "alt": "Shoes"},
    "images": [],
    "tags": ["running"],
    "keyword": "trail running shoes",
    "wordCount": 1200,
    "publishedAt": "2026-10-11T10:00:00.000Z",
    "publishedUrl": None,
}


def _signed(
    event: str, data: dict[str, object], *, secret: str = SECRET
) -> tuple[bytes, dict[str, str]]:
    body = json.dumps({"event": event, "data": data, "timestamp": "2026-10-11T10:00:00Z"}).encode()
    sent_at = str(int(time.time()))
    digest = hmac.new(secret.encode(), f"{sent_at}.".encode() + body, hashlib.sha256).hexdigest()
    return body, {
        "Content-Type": "application/json",
        "X-FoPost-Timestamp": sent_at,
        "X-FoPost-Signature-256": f"sha256={digest}",
        "X-FoPost-Event": event,
    }


def _app(callback: ArticleCallback) -> FastAPI:
    app = FastAPI()
    app.include_router(article_router(secret=SECRET, on_article_published=callback))
    return app


def test_a_signed_test_delivery_is_accepted() -> None:
    def never(article: ArticlePublishedPayload) -> None:  # pragma: no cover - must not run
        raise AssertionError("callback ran on article.test")

    body, headers = _signed("article.test", {})
    with TestClient(_app(never)) as client:
        response = client.post("/articles", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_a_tampered_delivery_is_rejected_before_the_callback() -> None:
    ran: list[str] = []

    def store(article: ArticlePublishedPayload) -> None:  # pragma: no cover - must not run
        ran.append(article.id)

    _, headers = _signed("article.published", ARTICLE)
    tampered, _ = _signed("article.published", {**ARTICLE, "id": "art_evil"})
    with TestClient(_app(store)) as client:
        response = client.post("/articles", content=tampered, headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid_signature"}
    assert ran == []


def test_a_published_article_reaches_the_callback_parsed() -> None:
    seen: list[ArticlePublishedPayload] = []

    async def store(article: ArticlePublishedPayload) -> str:
        seen.append(article)
        return f"https://yourbrand.com/blog/{article.slug}"

    body, headers = _signed("article.published", ARTICLE)
    with TestClient(_app(store)) as client:
        response = client.post("/articles", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"url": "https://yourbrand.com/blog/best-trail-running-shoes"}
    assert len(seen) == 1
    assert seen[0].title == "Best trail running shoes"
    assert seen[0].body_markdown == "# Shoes"
    assert seen[0].featured_image is not None
    assert seen[0].featured_image.media_id == "med_1"
    assert seen[0].word_count == 1200


def test_a_sync_callback_runs_too() -> None:
    def store(article: ArticlePublishedPayload) -> None:
        pass

    body, headers = _signed("article.published", ARTICLE)
    with TestClient(_app(store)) as client:
        response = client.post("/articles", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"ok": True}

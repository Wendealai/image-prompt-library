from __future__ import annotations

import json

import httpx
import pytest

from backend.schemas import NanobananaArticleImagesRequest, NanobananaImageRequest, NanobananaSourceItem
from backend.services.nanobanana import (
    NanobananaBatchFailed,
    NanobananaError,
    NanobananaTimeout,
    map_assets_by_slot,
    request_article_images,
    wait_for_article_images,
)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_request_article_images_sends_auth_idempotency_and_reference_items():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(202, json={
            "ok": True,
            "status": "queued",
            "batchId": "batch_123",
            "statusUrl": "https://image-api.test/v1/article-images/batch_123",
        })

    payload = NanobananaArticleImagesRequest(
        articleId="item_123",
        projectId="image-prompt-library",
        stylePack="gallery-clean",
        idempotencyKey="item_123:nanobanana-images:v1",
        images=[
            NanobananaImageRequest(
                id="cover",
                slot="cover",
                prompt="A clean poster of a ceramic lamp.",
                mode="image-to-image",
                sourceItems=[
                    NanobananaSourceItem(
                        label="lamp",
                        role="subject",
                        imageUrl="https://example.test/lamp.png",
                        mimeType="image/png",
                    )
                ],
            )
        ],
    )

    with _client(handler) as client:
        result = request_article_images(payload, api_base_url="https://image-api.test", api_token="secret-token", client=client)

    assert result["batchId"] == "batch_123"
    assert seen["method"] == "POST"
    assert seen["url"] == "https://image-api.test/v1/article-images"
    assert seen["headers"]["authorization"] == "Bearer secret-token"
    assert seen["headers"]["idempotency-key"] == "item_123:nanobanana-images:v1"
    assert seen["body"]["images"][0]["sourceItems"][0]["imageUrl"] == "https://example.test/lamp.png"
    assert "wait" not in seen["body"]
    assert "idempotencyKey" not in seen["body"]


def test_request_article_images_accepts_http_200_idempotent_replay():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "ok": True,
            "status": "queued",
            "batchId": "batch_replay",
            "statusUrl": "https://image-api.test/v1/article-images/batch_replay",
            "idempotentReplay": True,
        })

    payload = NanobananaArticleImagesRequest(
        articleId="item_123",
        projectId="image-prompt-library",
        idempotencyKey="stable-key",
        images=[NanobananaImageRequest(id="cover", slot="cover", prompt="A test image.")],
    )

    with _client(handler) as client:
        result = request_article_images(payload, api_base_url="https://image-api.test", api_token="secret-token", client=client)

    assert result["idempotentReplay"] is True
    assert result["batchId"] == "batch_replay"


def test_request_article_images_raises_on_http_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"ok": False, "error": "unauthorized"})

    payload = NanobananaArticleImagesRequest(
        articleId="item_123",
        projectId="image-prompt-library",
        idempotencyKey="stable-key",
        images=[NanobananaImageRequest(id="cover", slot="cover", prompt="A test image.")],
    )

    with _client(handler) as client:
        with pytest.raises(NanobananaError, match="HTTP 401"):
            request_article_images(payload, api_base_url="https://image-api.test", api_token="secret-token", client=client)


def test_wait_for_article_images_returns_completed_after_polling():
    responses = iter([
        {"ok": True, "batch": {"batchId": "batch_123", "status": "queued"}, "images": []},
        {"ok": True, "batch": {"batchId": "batch_123", "status": "running"}, "images": []},
        {
            "ok": True,
            "batch": {"batchId": "batch_123", "status": "completed"},
            "images": [{"slot": "cover", "status": "completed", "assets": [{"url": "https://image-api.test/a.png", "key": "k"}]}],
        },
    ])

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    with _client(handler) as client:
        result = wait_for_article_images(
            batch_id="batch_123",
            api_base_url="https://image-api.test",
            api_token="secret-token",
            client=client,
            sleep=lambda _seconds: None,
        )

    assert result["batch"]["status"] == "completed"
    assert result["images"][0]["assets"][0]["url"] == "https://image-api.test/a.png"


def test_wait_for_article_images_returns_partial_failed_as_usable():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "ok": True,
            "batch": {"batchId": "batch_123", "status": "partial_failed"},
            "images": [
                {"slot": "cover", "status": "completed", "assets": [{"url": "https://image-api.test/a.png", "key": "k"}]},
                {"slot": "section_1", "status": "failed", "assets": [], "error": "generation failed"},
            ],
        })

    with _client(handler) as client:
        result = wait_for_article_images(batch_id="batch_123", api_token="secret-token", client=client)

    assert result["batch"]["status"] == "partial_failed"


def test_wait_for_article_images_throws_on_failed_batch():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "batch": {"batchId": "batch_123", "status": "failed"}, "images": []})

    with _client(handler) as client:
        with pytest.raises(NanobananaBatchFailed):
            wait_for_article_images(batch_id="batch_123", api_token="secret-token", client=client)


def test_wait_for_article_images_throws_on_timeout():
    clock = iter([0.0, 0.0, 2.0])

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "batch": {"batchId": "batch_123", "status": "running"}, "images": []})

    with _client(handler) as client:
        with pytest.raises(NanobananaTimeout):
            wait_for_article_images(
                batch_id="batch_123",
                api_token="secret-token",
                client=client,
                timeout_ms=1000,
                poll_interval_ms=100,
                sleep=lambda _seconds: None,
                now=lambda: next(clock),
            )


def test_map_assets_by_slot_keeps_success_and_failure_details():
    mapped = map_assets_by_slot({
        "images": [
            {"itemId": "cover", "slot": "cover", "status": "completed", "assets": [{"assetId": "a1", "url": "https://image-api.test/a.png", "key": "k"}]},
            {"itemId": "section", "slot": "section_1", "status": "failed", "assets": [], "error": {"message": "bad prompt"}},
        ]
    })

    assert mapped["cover"]["url"] == "https://image-api.test/a.png"
    assert mapped["cover"]["key"] == "k"
    assert mapped["section_1"]["status"] == "failed"
    assert mapped["section_1"]["error"] == {"message": "bad prompt"}

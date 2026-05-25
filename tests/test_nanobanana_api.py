from __future__ import annotations

from fastapi.testclient import TestClient

from backend.db import connect
from backend.main import create_app
from backend.routers import nanobanana as nanobanana_router


def client(tmp_path):
    return TestClient(create_app(library_path=tmp_path / "library"))


def create_payload(**overrides):
    payload = {
        "title": "Generated Product Study",
        "model": "ChatGPT Image2",
        "cluster_name": "Nanobanana Tests",
        "prompts": [
            {"language": "en", "text": "A quiet studio product photo of a ceramic desk lamp.", "is_primary": True},
            {"language": "zh_hant", "text": "陶瓷檯燈的安靜棚拍產品照"},
        ],
    }
    payload.update(overrides)
    return payload


def test_article_images_endpoint_requires_server_side_token(tmp_path, monkeypatch):
    monkeypatch.delenv("NANOBANANA_IMAGE_API_TOKEN", raising=False)
    c = client(tmp_path)

    response = c.post(
        "/api/nanobanana/article-images",
        json={
            "articleId": "item_123",
            "projectId": "image-prompt-library",
            "idempotencyKey": "item_123:nanobanana-images:v1",
            "images": [{"id": "cover", "slot": "cover", "prompt": "A clean image."}],
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Nanobanana image API token is not configured."


def test_item_nanobanana_generation_uses_prompt_waits_and_stores_remote_asset(tmp_path, monkeypatch):
    c = client(tmp_path)
    item = c.post("/api/items", json=create_payload()).json()
    seen = {}

    def fake_request(payload):
        seen["article"] = payload.model_dump(by_alias=True, exclude_none=True)
        return {
            "ok": True,
            "status": "queued",
            "batchId": "batch_123",
            "statusUrl": "https://image-api.test/v1/article-images/batch_123",
        }

    def fake_wait(**kwargs):
        seen["wait"] = kwargs
        return {
            "ok": True,
            "batch": {"batchId": "batch_123", "status": "completed"},
            "images": [
                {
                    "itemId": "result_image",
                    "slot": "result_image",
                    "status": "completed",
                    "assets": [
                        {
                            "assetId": "asset_1",
                            "url": "https://image-api.test/assets/batch_123/result.png",
                            "key": "nanobanana/article-images/batch_123/result.png",
                            "mimeType": "image/png",
                            "sizeBytes": 1234,
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(nanobanana_router, "request_article_images", fake_request)
    monkeypatch.setattr(nanobanana_router, "wait_for_article_images", fake_wait)

    response = c.post(f"/api/items/{item['id']}/nanobanana/images", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["stored_images"][0]["remote_url"] == "https://image-api.test/assets/batch_123/result.png"
    assert body["mapped"]["result_image"]["url"] == "https://image-api.test/assets/batch_123/result.png"
    assert seen["article"]["articleId"] == item["id"]
    assert seen["article"]["projectId"] == "image-prompt-library"
    assert seen["article"]["images"][0]["prompt"] == "A quiet studio product photo of a ceramic desk lamp."
    assert seen["article"]["images"][0]["mode"] == "text-to-image"
    assert seen["article"]["idempotencyKey"].startswith(f"{item['id']}:nanobanana-images:v1:")
    assert seen["wait"]["batch_id"] == "batch_123"

    detail = c.get(f"/api/items/{item['id']}").json()
    assert detail["first_image"]["remote_url"] == "https://image-api.test/assets/batch_123/result.png"
    assert detail["first_image"]["original_path"] == "nanobanana/article-images/batch_123/result.png"


def test_item_nanobanana_generation_dedupes_idempotent_remote_asset(tmp_path, monkeypatch):
    c = client(tmp_path)
    item = c.post("/api/items", json=create_payload()).json()

    def fake_request(_payload):
        return {"ok": True, "status": "queued", "batchId": "batch_123"}

    def fake_wait(**_kwargs):
        return {
            "ok": True,
            "batch": {"batchId": "batch_123", "status": "completed"},
            "images": [
                {
                    "itemId": "result_image",
                    "slot": "result_image",
                    "status": "completed",
                    "assets": [{"url": "https://image-api.test/assets/batch_123/result.png"}],
                }
            ],
        }

    monkeypatch.setattr(nanobanana_router, "request_article_images", fake_request)
    monkeypatch.setattr(nanobanana_router, "wait_for_article_images", fake_wait)

    first = c.post(f"/api/items/{item['id']}/nanobanana/images", json={})
    second = c.post(f"/api/items/{item['id']}/nanobanana/images", json={})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["stored_images"][0]["id"] == second.json()["stored_images"][0]["id"]
    with connect(tmp_path / "library") as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM images WHERE item_id=? AND remote_url=?",
            (item["id"], "https://image-api.test/assets/batch_123/result.png"),
        ).fetchone()[0]
    assert count == 1


def test_item_nanobanana_generation_supports_override_prompt_and_references(tmp_path, monkeypatch):
    c = client(tmp_path)
    item = c.post("/api/items", json=create_payload()).json()
    seen = {}

    def fake_request(payload):
        seen["article"] = payload.model_dump(by_alias=True, exclude_none=True)
        return {"ok": True, "status": "queued", "batchId": "batch_123"}

    monkeypatch.setattr(nanobanana_router, "request_article_images", fake_request)

    response = c.post(
        f"/api/items/{item['id']}/nanobanana/images",
        json={
            "promptText": "Render this exact lamp as a catalog hero image.",
            "wait": False,
            "sourceItems": [
                {
                    "label": "lamp reference",
                    "role": "subject",
                    "imageUrl": "https://example.test/reference.png",
                    "mimeType": "image/png",
                }
            ],
        },
    )

    assert response.status_code == 200
    image = seen["article"]["images"][0]
    assert image["prompt"] == "Render this exact lamp as a catalog hero image."
    assert image["mode"] == "image-to-image"
    assert image["sourceItems"][0]["imageUrl"] == "https://example.test/reference.png"
    assert response.json()["terminal"] is None

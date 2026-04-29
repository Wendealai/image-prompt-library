import base64
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.repositories import ItemRepository
from backend.schemas import ItemCreate, PromptIn
from backend.services.image_generation import GeneratedImageBinary, ImageGenerationResult, ImageGenerationUnavailable, generate_images_from_prompt


PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO8T6ykAAAAASUVORK5CYII="
PNG_BYTES = base64.b64decode(PNG_BASE64)


def _create_item(repo: ItemRepository) -> str:
    item = repo.create_item(ItemCreate(
        title="Studio Poster",
        prompts=[PromptIn(language="en", text="A cinematic studio poster with reflective chrome lettering.", is_primary=True)],
    ))
    return item.id


def test_generate_images_from_prompt_handles_sync_images(monkeypatch):
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_IMAGE_GENERATE_WEBHOOK_URL", "https://n8n.example/webhook/img-generate-submit")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/webhook/img-generate-submit"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "status": "completed",
                "images": [
                    {
                        "src": f"data:image/png;base64,{PNG_BASE64}",
                        "mimeType": "image/png",
                    },
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        result = generate_images_from_prompt("A cinematic studio poster", client=client)

    assert result.status == "completed"
    assert result.job_id is None
    assert len(result.images) == 1
    assert result.images[0].data == PNG_BYTES
    assert result.images[0].mime_type == "image/png"


def test_generate_images_from_prompt_polls_job_status(monkeypatch):
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_IMAGE_GENERATE_WEBHOOK_URL", "https://n8n.example/webhook/img-generate-submit")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_IMAGE_STATUS_WEBHOOK_URL", "https://n8n.example/webhook/img-job-status")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_IMAGE_POLL_INTERVAL_SECONDS", "0.01")
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_IMAGE_POLL_TIMEOUT_SECONDS", "2")

    status_calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/webhook/img-generate-submit":
            return httpx.Response(202, json={"ok": True, "status": "accepted", "jobId": "job_123"})
        if request.url.path == "/webhook/img-job-status":
            status_calls["count"] += 1
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "images": [
                        {
                            "src": f"data:image/png;base64,{PNG_BASE64}",
                            "mimeType": "image/png",
                        },
                    ],
                },
            )
        raise AssertionError(f"Unexpected request URL: {request.url}")

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        result = generate_images_from_prompt("A neon storefront poster", client=client)

    assert result.job_id == "job_123"
    assert len(result.images) == 1
    assert status_calls["count"] == 1


def test_generate_image_endpoint_persists_generated_images(tmp_path: Path, monkeypatch):
    library = tmp_path / "library"
    app = create_app(library_path=library)
    client = TestClient(app)
    repo = ItemRepository(library)
    item_id = _create_item(repo)

    def fake_generate_images_from_prompt(prompt: str, *, item_id: str | None = None, title: str | None = None, client=None):
        assert prompt == "A polished chrome poster"
        assert item_id is not None
        assert title == "Studio Poster"
        return ImageGenerationResult(
            status="completed",
            job_id="job_saved",
            output_text=None,
            images=[GeneratedImageBinary(data=PNG_BYTES, mime_type="image/png", filename="generated.png")],
        )

    monkeypatch.setattr("backend.routers.prompt_templates.generate_images_from_prompt", fake_generate_images_from_prompt)

    response = client.post(f"/api/items/{item_id}/generate-image", json={"prompt": "A polished chrome poster"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["job_id"] == "job_saved"
    assert len(payload["images"]) == 1
    assert len(payload["item"]["images"]) == 1

    stored_original = library / payload["images"][0]["original_path"]
    stored_preview = library / payload["images"][0]["preview_path"]
    stored_thumb = library / payload["images"][0]["thumb_path"]
    assert stored_original.is_file()
    assert stored_preview.is_file()
    assert stored_thumb.is_file()


def test_generate_image_endpoint_returns_503_when_workflow_is_unavailable(tmp_path: Path, monkeypatch):
    library = tmp_path / "library"
    app = create_app(library_path=library)
    client = TestClient(app)
    repo = ItemRepository(library)
    item_id = _create_item(repo)

    def fake_generate_images_from_prompt(prompt: str, *, item_id: str | None = None, title: str | None = None, client=None):
        raise ImageGenerationUnavailable("Missing webhook URL")

    monkeypatch.setattr("backend.routers.prompt_templates.generate_images_from_prompt", fake_generate_images_from_prompt)

    response = client.post(f"/api/items/{item_id}/generate-image", json={"prompt": "A polished chrome poster"})
    assert response.status_code == 503
    assert response.json()["detail"] == "AI image generation workflow is not configured."

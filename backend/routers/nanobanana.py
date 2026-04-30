from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.repositories import ItemRepository
from backend.schemas import (
    ImageRecord,
    NanobananaArticleImagesRequest,
    NanobananaDefaults,
    NanobananaImageRequest,
    NanobananaItemImageGenerationRequest,
)
from backend.services.nanobanana import (
    NanobananaBatchFailed,
    NanobananaError,
    NanobananaTimeout,
    NanobananaUnavailable,
    map_assets_by_slot,
    query_article_images,
    request_article_images,
    wait_for_article_images,
)

router = APIRouter()


def repo(request: Request) -> ItemRepository:
    return ItemRepository(request.app.state.library_path)


def _handle_nanobanana_error(exc: Exception):
    if isinstance(exc, NanobananaUnavailable):
        raise HTTPException(status_code=503, detail="Nanobanana image API token is not configured.") from exc
    if isinstance(exc, NanobananaTimeout):
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    if isinstance(exc, NanobananaBatchFailed):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if isinstance(exc, NanobananaError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise exc


def _terminal_payload(create_payload: dict[str, Any], request_payload: NanobananaArticleImagesRequest) -> dict[str, Any] | None:
    if not request_payload.wait:
        return None
    batch_id = str(create_payload.get("batchId") or "")
    status_url = create_payload.get("statusUrl")
    if not batch_id:
        raise HTTPException(status_code=502, detail="Nanobanana create response did not include batchId.")
    return wait_for_article_images(
        batch_id=batch_id,
        status_url=status_url if isinstance(status_url, str) else None,
        timeout_ms=request_payload.timeout_ms,
        poll_interval_ms=request_payload.poll_interval_ms,
    )


def _first_matching_prompt(item, language: str | None) -> str:
    usable_prompts = [prompt for prompt in item.prompts if prompt.text.strip()]
    if not usable_prompts:
        raise HTTPException(status_code=400, detail="This item does not have a usable prompt yet.")
    if language:
        for prompt in usable_prompts:
            if prompt.language == language:
                return prompt.text
        raise HTTPException(status_code=400, detail=f"Prompt language not found: {language}")
    primary_prompt = next((prompt for prompt in usable_prompts if prompt.is_primary), None)
    return (primary_prompt or usable_prompts[0]).text


def _item_idempotency_key(item_id: str, prompt: str, payload: NanobananaItemImageGenerationRequest) -> str:
    if payload.idempotency_key:
        return payload.idempotency_key
    fingerprint_payload = {
        "prompt": prompt,
        "generation": payload.generation.model_dump(by_alias=True, exclude_none=True) if payload.generation else None,
        "sourceItems": [item.model_dump(by_alias=True, exclude_none=True) for item in payload.source_items],
        "stylePack": payload.style_pack,
    }
    fingerprint = hashlib.sha256(json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    return f"{item_id}:nanobanana-images:v1:{fingerprint}"


def _stored_images_from_payload(repository: ItemRepository, item_id: str, terminal_payload: dict[str, Any] | None) -> list[ImageRecord]:
    if not terminal_payload:
        return []
    stored: list[ImageRecord] = []
    for image in terminal_payload.get("images") or []:
        if not isinstance(image, dict) or image.get("status") != "completed":
            continue
        assets = image.get("assets") if isinstance(image.get("assets"), list) else []
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            url = asset.get("url")
            if not isinstance(url, str) or not url.strip():
                continue
            stored.append(repository.add_remote_image(item_id, url, storage_key=asset.get("key"), role="result_image"))
    return stored


@router.post("/nanobanana/article-images")
def create_nanobanana_article_images(payload: NanobananaArticleImagesRequest):
    try:
        create_payload = request_article_images(payload)
        terminal_payload = _terminal_payload(create_payload, payload)
        return {
            "create": create_payload,
            "terminal": terminal_payload,
            "mapped": map_assets_by_slot(terminal_payload or create_payload),
        }
    except Exception as exc:  # noqa: BLE001
        _handle_nanobanana_error(exc)


@router.get("/nanobanana/article-images/{batch_id}")
def get_nanobanana_article_images(batch_id: str):
    try:
        payload = query_article_images(batch_id)
        return {"batch": payload, "mapped": map_assets_by_slot(payload)}
    except Exception as exc:  # noqa: BLE001
        _handle_nanobanana_error(exc)


@router.post("/items/{item_id}/nanobanana/images")
def generate_item_images(request: Request, item_id: str, payload: NanobananaItemImageGenerationRequest):
    repository = repo(request)
    try:
        item = repository.get_item(item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Item not found") from exc

    prompt = (payload.prompt_text or "").strip() or _first_matching_prompt(item, payload.prompt_language)
    mode = "image-to-image" if payload.source_items else "text-to-image"
    image_request = NanobananaImageRequest(
        id="result_image",
        slot="result_image",
        mode=mode,
        prompt=prompt,
        generation=payload.generation,
        sourceItems=payload.source_items,
    )
    article_request = NanobananaArticleImagesRequest(
        articleId=item.id,
        projectId="image-prompt-library",
        stylePack=payload.style_pack,
        idempotencyKey=_item_idempotency_key(item.id, prompt, payload),
        defaults=NanobananaDefaults(),
        images=[image_request],
        metadata={
            "sourceWorkflow": "image-prompt-library",
            "itemId": item.id,
            "itemTitle": item.title,
        },
        wait=payload.wait,
        timeoutMs=payload.timeout_ms,
        pollIntervalMs=payload.poll_interval_ms,
    )
    try:
        create_payload = request_article_images(article_request)
        terminal_payload = _terminal_payload(create_payload, article_request)
        stored_images = _stored_images_from_payload(repository, item.id, terminal_payload)
        return {
            "create": create_payload,
            "terminal": terminal_payload,
            "mapped": map_assets_by_slot(terminal_payload or create_payload),
            "stored_images": stored_images,
        }
    except Exception as exc:  # noqa: BLE001
        _handle_nanobanana_error(exc)

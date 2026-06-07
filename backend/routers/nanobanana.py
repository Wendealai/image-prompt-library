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


def _batch_id_from_payload(payload: dict[str, Any]) -> str:
    batch_id = payload.get("batchId") or payload.get("batch_id")
    return batch_id.strip() if isinstance(batch_id, str) else ""


def _job_id_from_payload(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("jobId", "job_id", "n8nJobId", "n8n_job_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    batch = payload.get("batch")
    if isinstance(batch, dict):
        for key in ("jobId", "job_id", "n8nJobId", "n8n_job_id"):
            value = batch.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _generation_options_metadata(payload: NanobananaItemImageGenerationRequest) -> dict[str, Any]:
    return payload.generation.model_dump(by_alias=True, exclude_none=True) if payload.generation else {}


def _reference_metadata(payload: NanobananaItemImageGenerationRequest) -> list[dict[str, Any]]:
    return [item.model_dump(by_alias=True, exclude_none=True) for item in payload.source_items]


def _result_slot_payload(payload: dict[str, Any]) -> dict[str, Any]:
    mapped = map_assets_by_slot(payload)
    result = mapped.get("result_image")
    return result if isinstance(result, dict) else {}


def _status_from_payload(payload: dict[str, Any]) -> str:
    result = _result_slot_payload(payload)
    result_status = result.get("status")
    if isinstance(result_status, str) and result_status.strip():
        return result_status.strip()
    batch = payload.get("batch")
    if isinstance(batch, dict):
        batch_status = batch.get("status")
        if isinstance(batch_status, str) and batch_status.strip():
            return batch_status.strip()
    top_level = payload.get("status")
    if isinstance(top_level, str) and top_level.strip():
        return top_level.strip()
    return "queued"


def _error_metadata_from_payload(payload: dict[str, Any]) -> tuple[str | None, str | None, dict[str, Any]]:
    result = _result_slot_payload(payload)
    raw_error = result.get("error")
    if isinstance(raw_error, dict):
        details = raw_error.get("details")
        if isinstance(details, dict):
            normalized_details = details
        elif details is None:
            normalized_details = {}
        else:
            normalized_details = {"raw": details}
        code = raw_error.get("code")
        message = raw_error.get("message")
        return (
            str(code).strip() or None if code is not None else None,
            str(message).strip() or None if message is not None else None,
            normalized_details,
        )
    batch = payload.get("batch")
    if isinstance(batch, dict):
        message = batch.get("message") or batch.get("error")
        if isinstance(message, str) and message.strip():
            return None, message.strip(), {}
    return None, None, {}


def _update_direct_generation_run(
    repository: ItemRepository,
    *,
    item_id: str,
    batch_id: str,
    job_id: str | None = None,
    status: str | None = None,
    image_ids: list[str] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    error_details: dict[str, Any] | None = None,
):
    run = repository.find_prompt_image_generation_run_by_batch(item_id, batch_id)
    if run is None:
        return None
    return repository.update_prompt_image_generation_run(
        run.id,
        batch_id=batch_id,
        job_id=job_id,
        status=status,
        image_ids=image_ids,
        error_code=error_code if error_code is not None else run.error_code,
        error_message=error_message if error_message is not None else run.error_message,
        error_details=error_details if error_details is not None else run.error_details,
    )


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


@router.get("/items/{item_id}/nanobanana/images/{batch_id}")
def get_item_nanobanana_images(request: Request, item_id: str, batch_id: str):
    repository = repo(request)
    try:
        repository.get_item(item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Item not found") from exc

    try:
        payload = query_article_images(batch_id)
        stored_images = _stored_images_from_payload(repository, item_id, payload)
        status = _status_from_payload(payload)
        error_code, error_message, error_details = _error_metadata_from_payload(payload)
        clear_errors = bool(stored_images) or status == "completed"
        run = _update_direct_generation_run(
            repository,
            item_id=item_id,
            batch_id=batch_id,
            job_id=_job_id_from_payload(payload),
            status=status,
            image_ids=[image.id for image in stored_images],
            error_code="" if clear_errors else error_code,
            error_message="" if clear_errors else error_message,
            error_details={} if clear_errors else error_details,
        )
        return {
            "batch": payload,
            "mapped": map_assets_by_slot(payload),
            "stored_images": stored_images,
            "run": run,
        }
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
        stored_images = _stored_images_from_payload(repository, item.id, terminal_payload or create_payload)
        batch_id = _batch_id_from_payload(create_payload)
        if not stored_images and not article_request.wait and not batch_id:
            raise HTTPException(status_code=502, detail="Nanobanana create response did not include a batchId or image data.")
        status_payload = terminal_payload or create_payload
        status = _status_from_payload(status_payload)
        error_code, error_message, error_details = _error_metadata_from_payload(status_payload)
        clear_errors = bool(stored_images) or status == "completed"
        run = repository.add_prompt_image_generation_run(
            item_id=item.id,
            prompt=prompt,
            generation_options=_generation_options_metadata(payload),
            references=_reference_metadata(payload),
            source="direct",
            batch_id=batch_id or None,
            job_id=_job_id_from_payload(status_payload),
            status=status,
            image_ids=[image.id for image in stored_images],
            error_code=None if clear_errors else error_code,
            error_message=None if clear_errors else error_message,
            error_details={} if clear_errors else error_details,
        )
        return {
            "create": create_payload,
            "terminal": terminal_payload,
            "mapped": map_assets_by_slot(terminal_payload or create_payload),
            "stored_images": stored_images,
            "run": run,
        }
    except Exception as exc:  # noqa: BLE001
        _handle_nanobanana_error(exc)

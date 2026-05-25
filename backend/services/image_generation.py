from __future__ import annotations

import base64
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

GENERATE_URL_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_GENERATE_WEBHOOK_URL"
STATUS_URL_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_STATUS_WEBHOOK_URL"
TOKEN_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_WORKFLOW_TOKEN"
TOKEN_HEADER_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_WORKFLOW_TOKEN_HEADER"
TIMEOUT_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_TIMEOUT_SECONDS"
POLL_INTERVAL_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_POLL_INTERVAL_SECONDS"
POLL_TIMEOUT_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_POLL_TIMEOUT_SECONDS"
PROVIDER_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_PROVIDER"
MODEL_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_MODEL"
TOOL_MODEL_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_TOOL_MODEL"
RESOLUTION_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_RESOLUTION"
ASPECT_RATIO_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_ASPECT_RATIO"
QUALITY_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_QUALITY"
OUTPUT_FORMAT_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_OUTPUT_FORMAT"
BACKGROUND_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_BACKGROUND"
STYLE_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_STYLE"
TEMPERATURE_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_TEMPERATURE"
IMAGE_COUNT_ENV = "IMAGE_PROMPT_LIBRARY_IMAGE_COUNT"

DEFAULT_TOKEN_HEADER = "X-N8N-Token"
DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_TOOL_MODEL = "gpt-image-2"
DEFAULT_RESOLUTION = "1024x1024"
DEFAULT_ASPECT_RATIO = "1:1"
DEFAULT_QUALITY = "high"
DEFAULT_OUTPUT_FORMAT = "jpg"
DEFAULT_BACKGROUND = "auto"
DEFAULT_STYLE = "auto"
DEFAULT_IMAGE_TO_IMAGE_STRENGTH = 0.65
MAX_REFERENCE_IMAGES = 16


class ImageGenerationUnavailable(RuntimeError):
    pass


class ImageGenerationError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        url: str | None = None,
        request_payload: dict[str, Any] | None = None,
        response_status: int | None = None,
        response_text: str | None = None,
        job_id: str | None = None,
        execution_status: str | None = None,
    ):
        super().__init__(message)
        self.operation = operation
        self.url = url
        self.request_payload = request_payload
        self.response_status = response_status
        self.response_text = response_text
        self.job_id = job_id
        self.execution_status = execution_status


@dataclass
class GeneratedImageBinary:
    data: bytes
    mime_type: str
    filename: str
    remote_url: str | None = None


@dataclass
class ImageGenerationResult:
    status: str
    job_id: str | None
    output_text: str | None
    images: list[GeneratedImageBinary]


def _is_record(value: Any) -> bool:
    return isinstance(value, dict)


def _workflow_url(env_name: str) -> str:
    url = os.environ.get(env_name, "").strip()
    if not url:
        raise ImageGenerationUnavailable(f"{env_name} is not configured.")
    return url


def _workflow_headers() -> dict[str, str]:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        return {}
    header_name = os.environ.get(TOKEN_HEADER_ENV, DEFAULT_TOKEN_HEADER).strip() or DEFAULT_TOKEN_HEADER
    if header_name.lower() == "authorization":
        return {header_name: f"Bearer {token}"}
    return {header_name: token}


def _float_env(env_name: str, default: float, *, minimum: float) -> float:
    raw_value = os.environ.get(env_name, str(default)).strip()
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ImageGenerationError(f"Invalid {env_name}: {raw_value}") from exc
    return max(minimum, value)


def _int_env(env_name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw_value = os.environ.get(env_name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ImageGenerationError(f"Invalid {env_name}: {raw_value}") from exc
    return min(maximum, max(minimum, value))


def _generation_temperature() -> float:
    return _float_env(TEMPERATURE_ENV, 0.7, minimum=0.0)


def _request_timeout_seconds() -> float:
    return _float_env(TIMEOUT_ENV, 60.0, minimum=5.0)


def _poll_interval_seconds() -> float:
    return _float_env(POLL_INTERVAL_ENV, 2.0, minimum=0.4)


def _poll_timeout_seconds() -> float:
    return _float_env(POLL_TIMEOUT_ENV, 150.0, minimum=10.0)


def _safe_json_parse(raw: str) -> Any:
    if not raw.strip():
        return {}
    try:
        return httpx.Response(200, text=raw).json()
    except ValueError:
        return raw


def _read_string_by_path(payload: Any, path: list[str]) -> str:
    cursor: Any = payload
    for segment in path:
        if not _is_record(cursor):
            return ""
        cursor = cursor.get(segment)
    return cursor.strip() if isinstance(cursor, str) else ""


def _pick_string_from_paths(payload: Any, paths: list[list[str]]) -> str:
    for path in paths:
        value = _read_string_by_path(payload, path)
        if value:
            return value
    return ""


def _looks_like_image_url(value: str) -> bool:
    trimmed = value.strip()
    if trimmed.startswith("data:image/"):
        return True
    return trimmed.startswith("http://") or trimmed.startswith("https://")


def _extract_text(payload: Any) -> str:
    snippets: list[str] = []
    visited: set[int] = set()

    def push(value: str) -> None:
        text = value.strip()
        if len(text) < 2 or _looks_like_image_url(text):
            return
        if text not in snippets:
            snippets.append(text)

    def walk(node: Any) -> None:
        if len(snippets) >= 12:
            return
        if isinstance(node, str):
            push(node)
            return
        node_id = id(node)
        if node_id in visited:
            return
        if isinstance(node, list):
            visited.add(node_id)
            for value in node:
                walk(value)
            return
        if not _is_record(node):
            return
        visited.add(node_id)
        for key in ("output_text", "text", "message", "error", "response", "content"):
            value = node.get(key)
            if isinstance(value, str):
                push(value)
        for value in node.values():
            walk(value)

    walk(payload)
    return "\n".join(snippets)[:6000]


def _make_data_url(value: str, mime_type: str | None = None) -> str:
    normalized = "".join(value.split())
    mime = (mime_type or "image/png").strip() or "image/png"
    return f"data:{mime};base64,{normalized}"


def _parse_json_like_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    trimmed = value.strip()
    if not trimmed or trimmed.startswith("data:image/"):
        return value
    if trimmed.startswith("{") or trimmed.startswith("["):
        return _safe_json_parse(trimmed)
    return value


def _extract_image_sources(payload: Any) -> list[tuple[str, str]]:
    images: list[tuple[str, str]] = []
    seen: set[str] = set()
    visited: set[int] = set()

    def add(src: str, mime_type: str | None = None) -> None:
        normalized = src.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        images.append((normalized, (mime_type or "image/png").strip() or "image/png"))

    def walk(node: Any) -> None:
        if isinstance(node, str):
            parsed = _parse_json_like_string(node)
            if parsed is not node:
                walk(parsed)
                return
            if _looks_like_image_url(node):
                add(node)
            return
        node_id = id(node)
        if node_id in visited:
            return
        if isinstance(node, list):
            visited.add(node_id)
            for value in node:
                walk(value)
            return
        if not _is_record(node):
            return
        visited.add(node_id)

        mime_type = node.get("mimeType") if isinstance(node.get("mimeType"), str) else node.get("mime_type")
        image_like = node.get("src") or node.get("url")
        if isinstance(image_like, str) and _looks_like_image_url(image_like):
            add(image_like, mime_type if isinstance(mime_type, str) else None)

        if node.get("type") == "image_generation_call":
            result = node.get("result")
            output_format = node.get("output_format") if isinstance(node.get("output_format"), str) else ""
            result_mime_type = mime_type if isinstance(mime_type, str) else ("image/jpeg" if output_format.lower() == "jpeg" else "image/png")
            if isinstance(result, str) and len(result.strip()) > 40:
                parsed = _parse_json_like_string(result)
                if parsed is not result:
                    walk(parsed)
                elif result.startswith("data:image/"):
                    add(result, result_mime_type)
                else:
                    add(_make_data_url(result, result_mime_type), result_mime_type)

        for inline_key in ("inlineData", "inline_data"):
            inline_value = node.get(inline_key)
            if _is_record(inline_value):
                data = inline_value.get("data")
                inline_mime = inline_value.get("mimeType") or inline_value.get("mime_type") or mime_type
                if isinstance(data, str) and len(data.strip()) > 40:
                    add(_make_data_url(data, inline_mime if isinstance(inline_mime, str) else None), inline_mime if isinstance(inline_mime, str) else None)

        for key in ("b64_json", "b64", "image_base64", "imageBase64", "base64", "image"):
            value = node.get(key)
            if isinstance(value, str) and len(value.strip()) > 40:
                add(_make_data_url(value, mime_type if isinstance(mime_type, str) else None), mime_type if isinstance(mime_type, str) else None)

        for value in node.values():
            walk(value)

    walk(payload)
    return images


def _filename_for_image(src: str, mime_type: str) -> str:
    if src.startswith("http://") or src.startswith("https://"):
        path = urlparse(src).path
        suffix = path.rsplit("/", 1)[-1].strip()
        if suffix and "." in suffix:
            return suffix
    extension = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(mime_type.lower(), ".png")
    return f"generated{extension}"


def _decode_data_url(src: str) -> tuple[bytes, str]:
    try:
        header, encoded = src.split(",", 1)
    except ValueError as exc:
        raise ImageGenerationError("Generated image data URL is invalid.") from exc
    mime_type = "image/png"
    if header.startswith("data:"):
        mime_type = header[5:].split(";", 1)[0].strip() or mime_type
    try:
        return base64.b64decode(encoded), mime_type
    except ValueError as exc:
        raise ImageGenerationError("Generated image base64 payload is invalid.") from exc


def _download_image_source(http_client: httpx.Client, src: str, mime_type: str) -> GeneratedImageBinary:
    if src.startswith("data:image/"):
        data, detected_mime = _decode_data_url(src)
        resolved_mime = detected_mime or mime_type
        return GeneratedImageBinary(
            data=data,
            mime_type=resolved_mime,
            filename=_filename_for_image(src, resolved_mime),
        )

    try:
        response = http_client.get(src, timeout=_request_timeout_seconds())
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ImageGenerationError(f"Failed to download generated image: {exc}") from exc

    resolved_mime = response.headers.get("content-type", "").split(";", 1)[0].strip() or mime_type
    return GeneratedImageBinary(
        data=response.content,
        mime_type=resolved_mime or "image/png",
        filename=_filename_for_image(src, resolved_mime or mime_type or "image/png"),
        remote_url=src,
    )


def _resolve_generated_images(http_client: httpx.Client, payload: Any) -> list[GeneratedImageBinary]:
    return [_download_image_source(http_client, src, mime_type) for src, mime_type in _extract_image_sources(payload)]


def _reference_string(reference: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = reference.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_reference_images(reference_images: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, reference in enumerate(reference_images or []):
        if not _is_record(reference):
            continue
        image_base64 = _reference_string(reference, "image_base64", "imageBase64")
        image_url = _reference_string(reference, "image_url", "imageUrl")
        if not image_base64 and not image_url:
            continue
        mime_type = _reference_string(reference, "mime_type", "mimeType") or "image/png"
        item: dict[str, Any] = {
            "type": "file-base64" if image_base64 else "url",
            "label": _reference_string(reference, "label") or ("primary" if index == 0 else f"reference {index + 1}"),
            "role": _reference_string(reference, "role") or ("subject" if index == 0 else "style"),
        }
        note = _reference_string(reference, "note")
        if note:
            item["note"] = note
        if image_base64:
            item["mimeType"] = mime_type
            item["imageBase64"] = image_base64
        if image_url:
            item["imageUrl"] = image_url
        normalized.append(item)
        if len(normalized) >= MAX_REFERENCE_IMAGES:
            break
    return normalized


def _generation_strength(normalized_generation: dict[str, Any], *, has_references: bool) -> float:
    if not has_references:
        return 1.0
    default = DEFAULT_IMAGE_TO_IMAGE_STRENGTH if has_references else 1.0
    raw_value = normalized_generation.get("strength")
    if raw_value is None or raw_value == "":
        return default
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ImageGenerationError(f"Invalid image generation strength: {raw_value}") from exc
    return min(1.0, max(0.0, value))


def _generation_output_format(normalized_generation: dict[str, Any]) -> str:
    raw_value = str(normalized_generation.get("output_format") or os.environ.get(OUTPUT_FORMAT_ENV, DEFAULT_OUTPUT_FORMAT)).strip().lower()
    if raw_value in {"jpg", "jpeg"}:
        return "jpeg"
    if raw_value == "png":
        return "png"
    raise ImageGenerationError(f"Invalid image output format: {raw_value}")


def _extract_job_id(payload: Any) -> str:
    return _pick_string_from_paths(payload, [
        ["jobId"],
        ["job_id"],
        ["id"],
        ["data", "jobId"],
        ["data", "job_id"],
        ["result", "jobId"],
        ["result", "job_id"],
    ])


def _extract_status(payload: Any) -> str:
    return _pick_string_from_paths(payload, [
        ["status"],
        ["state"],
        ["jobStatus"],
        ["data", "status"],
        ["data", "state"],
        ["result", "status"],
        ["result", "state"],
    ])


def _extract_message(payload: Any) -> str:
    direct = _pick_string_from_paths(payload, [
        ["message"],
        ["error"],
        ["data", "message"],
        ["data", "error"],
        ["result", "message"],
        ["result", "error"],
    ])
    return direct or _extract_text(payload)


def _is_terminal_failure_status(status: str) -> bool:
    normalized = status.strip().lower()
    if not normalized:
        return False
    return (
        normalized in {"no_image", "no_images", "not_found", "not_configured", "http_error"}
        or normalized.startswith("upstream_")
        or "unavailable" in normalized
        or "unsupported" in normalized
        or "invalid" in normalized
        or "fail" in normalized
        or "error" in normalized
        or "cancel" in normalized
        or "timeout" in normalized
    )


def _is_terminal_success_status(status: str) -> bool:
    return any(token in status.strip().lower() for token in ("done", "success", "complete"))


def _parse_json_response(
    response: httpx.Response,
    *,
    operation: str,
    url: str,
    request_payload: dict[str, Any] | None,
    job_id: str | None = None,
) -> Any:
    if not response.is_success:
        detail = response.text.strip() or response.reason_phrase
        raise ImageGenerationError(
            f"Workflow request failed: {detail}",
            operation=operation,
            url=url,
            request_payload=request_payload,
            response_status=response.status_code,
            response_text=detail,
            job_id=job_id,
        )
    try:
        return response.json()
    except ValueError as exc:
        raise ImageGenerationError(
            "Workflow response must be valid JSON.",
            operation=operation,
            url=url,
            request_payload=request_payload,
            response_status=response.status_code,
            response_text=response.text,
            job_id=job_id,
        ) from exc


def _poll_job_until_done(http_client: httpx.Client, headers: dict[str, str], job_id: str) -> ImageGenerationResult:
    status_url = _workflow_url(STATUS_URL_ENV)
    started_at = time.monotonic()
    last_status = "pending"
    last_payload: Any = {}
    request_payload = {"jobId": job_id}

    while time.monotonic() - started_at < _poll_timeout_seconds():
        try:
            response = http_client.post(
                status_url,
                json=request_payload,
                headers=headers,
                timeout=_request_timeout_seconds(),
            )
        except httpx.HTTPError as exc:
            raise ImageGenerationError(
                f"Workflow status poll failed: {exc}",
                operation="image_status",
                url=status_url,
                request_payload=request_payload,
                job_id=job_id,
            ) from exc

        payload = _parse_json_response(
            response,
            operation="image_status",
            url=status_url,
            request_payload=request_payload,
            job_id=job_id,
        )
        last_payload = payload
        images = _resolve_generated_images(http_client, payload)
        output_text = _extract_text(payload)
        status = (_extract_status(payload) or ("completed" if images else "pending")).strip().lower()
        last_status = status or last_status

        if images:
            return ImageGenerationResult(
                status=status or "completed",
                job_id=job_id,
                output_text=output_text or None,
                images=images,
            )

        if _is_terminal_failure_status(status):
            detail = _extract_message(payload) or f"Image generation failed with status: {status}"
            raise ImageGenerationError(
                detail,
                operation="image_status",
                url=status_url,
                request_payload=request_payload,
                response_status=response.status_code,
                response_text=str(payload)[:200000],
                job_id=job_id,
                execution_status=status,
            )
        if _is_terminal_success_status(status):
            raise ImageGenerationError(
                "Image generation finished without returning a usable image.",
                operation="image_status",
                url=status_url,
                request_payload=request_payload,
                response_status=response.status_code,
                response_text=str(payload)[:200000],
                job_id=job_id,
                execution_status=status,
            )

        time.sleep(_poll_interval_seconds())

    raise ImageGenerationError(
        f"Image generation polling timed out after {int(_poll_timeout_seconds())}s.",
        operation="image_status",
        url=status_url,
        request_payload=request_payload,
        response_text=str(last_payload)[:200000],
        job_id=job_id,
        execution_status=last_status,
    )


def _build_generate_payload(
    prompt: str,
    *,
    item_id: str | None = None,
    title: str | None = None,
    generation_options: dict[str, Any] | None = None,
    reference_images: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_generation = generation_options or {}
    reference_items = _normalize_reference_images(reference_images)
    mode = "image-to-image" if reference_items else "text-to-image"
    if reference_images and not reference_items:
        raise ValueError("Image-to-image requires at least one usable reference image.")
    payload: dict[str, Any] = {
        "requestId": str(uuid.uuid4()),
        "mode": mode,
        "provider": os.environ.get(PROVIDER_ENV, DEFAULT_PROVIDER).strip() or DEFAULT_PROVIDER,
        "model": os.environ.get(MODEL_ENV, DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        "toolModel": os.environ.get(TOOL_MODEL_ENV, DEFAULT_TOOL_MODEL).strip() or DEFAULT_TOOL_MODEL,
        "prompt": prompt,
        "promptRaw": prompt,
        "negativePrompt": "",
        "stream": True,
        "generation": {
            "resolution": str(normalized_generation.get("resolution") or os.environ.get(RESOLUTION_ENV, DEFAULT_RESOLUTION)).strip() or DEFAULT_RESOLUTION,
            "aspectRatio": str(normalized_generation.get("aspect_ratio") or os.environ.get(ASPECT_RATIO_ENV, DEFAULT_ASPECT_RATIO)).strip() or DEFAULT_ASPECT_RATIO,
            "imageCount": int(normalized_generation.get("image_count") or _int_env(IMAGE_COUNT_ENV, 1, minimum=1, maximum=4)),
            "quality": os.environ.get(QUALITY_ENV, DEFAULT_QUALITY).strip() or DEFAULT_QUALITY,
            "outputFormat": _generation_output_format(normalized_generation),
            "background": os.environ.get(BACKGROUND_ENV, DEFAULT_BACKGROUND).strip() or DEFAULT_BACKGROUND,
            "style": str(normalized_generation.get("style") or os.environ.get(STYLE_ENV, DEFAULT_STYLE)).strip() or DEFAULT_STYLE,
            "temperature": round(_generation_temperature(), 2),
            "seed": None,
            "strength": _generation_strength(normalized_generation, has_references=bool(reference_items)),
        },
    }
    if reference_items:
        payload["source"] = reference_items[0]
        payload["sources"] = reference_items
        payload["sourceItems"] = reference_items
        payload["sourceCount"] = len(reference_items)
    if item_id or title:
        payload["metadata"] = {k: v for k, v in {"itemId": item_id, "title": title}.items() if v}
    return payload


def generate_images_from_prompt(
    prompt: str,
    *,
    item_id: str | None = None,
    title: str | None = None,
    generation_options: dict[str, Any] | None = None,
    reference_images: list[dict[str, Any]] | None = None,
    client: httpx.Client | None = None,
) -> ImageGenerationResult:
    cleaned_prompt = prompt.strip()
    if not cleaned_prompt:
        raise ValueError("Prompt is required.")

    generate_url = _workflow_url(GENERATE_URL_ENV)
    request_payload = _build_generate_payload(
        cleaned_prompt,
        item_id=item_id,
        title=title,
        generation_options=generation_options,
        reference_images=reference_images,
    )
    headers = {"Content-Type": "application/json", **_workflow_headers()}

    owns_client = client is None
    http_client = client or httpx.Client(follow_redirects=True)

    try:
        try:
            response = http_client.post(
                generate_url,
                json=request_payload,
                headers=headers,
                timeout=_request_timeout_seconds(),
            )
        except httpx.HTTPError as exc:
            raise ImageGenerationError(
                f"Workflow request failed: {exc}",
                operation="image_generate",
                url=generate_url,
                request_payload=request_payload,
            ) from exc

        payload = _parse_json_response(
            response,
            operation="image_generate",
            url=generate_url,
            request_payload=request_payload,
        )
        images = _resolve_generated_images(http_client, payload)
        status = (_extract_status(payload) or ("completed" if images else "pending")).strip().lower()
        job_id = _extract_job_id(payload) or None
        output_text = _extract_text(payload) or None

        if images:
            return ImageGenerationResult(
                status=status or "completed",
                job_id=job_id,
                output_text=output_text,
                images=images,
            )

        if job_id:
            return _poll_job_until_done(http_client, headers, job_id)

        detail = _extract_message(payload) or "Image workflow returned no images."
        raise ImageGenerationError(
            detail,
            operation="image_generate",
            url=generate_url,
            request_payload=request_payload,
            response_status=response.status_code,
            response_text=str(payload)[:200000],
            execution_status=status or None,
        )
    finally:
        if owns_client:
            http_client.close()

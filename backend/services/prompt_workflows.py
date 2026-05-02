from __future__ import annotations

import os
from typing import Any

import httpx

from backend.schemas import PromptGenerationVariantRecord, PromptTemplateRecord

INIT_URL_ENV = "IMAGE_PROMPT_TEMPLATE_INIT_WEBHOOK_URL"
GENERATE_URL_ENV = "IMAGE_PROMPT_TEMPLATE_GENERATE_WEBHOOK_URL"
TOKEN_ENV = "IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN"
TOKEN_HEADER_ENV = "IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN_HEADER"
TIMEOUT_ENV = "IMAGE_PROMPT_TEMPLATE_TIMEOUT_SECONDS"
DEFAULT_TOKEN_HEADER = "X-Image-Prompt-Workflow-Token"
INIT_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
INIT_MAX_ATTEMPTS = 2


class PromptWorkflowUnavailable(RuntimeError):
    pass


class PromptWorkflowError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        url: str | None = None,
        request_payload: dict[str, Any] | None = None,
        response_status: int | None = None,
        response_text: str | None = None,
    ):
        super().__init__(message)
        self.operation = operation
        self.url = url
        self.request_payload = request_payload
        self.response_status = response_status
        self.response_text = response_text


def _workflow_url(env_name: str) -> str:
    url = os.environ.get(env_name, "").strip()
    if not url:
        raise PromptWorkflowUnavailable(f"{env_name} is not configured.")
    return url


def _workflow_headers() -> dict[str, str]:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        return {}
    header_name = os.environ.get(TOKEN_HEADER_ENV, DEFAULT_TOKEN_HEADER).strip() or DEFAULT_TOKEN_HEADER
    if header_name.lower() == "authorization":
        return {header_name: f"Bearer {token}"}
    return {header_name: token}


def _timeout_seconds() -> float:
    raw_value = os.environ.get(TIMEOUT_ENV, "45").strip()
    try:
        timeout = float(raw_value)
    except ValueError as exc:
        raise PromptWorkflowError(f"Invalid {TIMEOUT_ENV}: {raw_value}") from exc
    return max(5.0, timeout)


def _post_json(url: str, payload: dict[str, Any], *, operation: str) -> dict[str, Any]:
    request_payload = payload
    headers = {"Content-Type": "application/json", **_workflow_headers()}
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=_timeout_seconds())
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip() or exc.response.reason_phrase
        raise PromptWorkflowError(
            f"Workflow request failed: {detail}",
            operation=operation,
            url=url,
            request_payload=request_payload,
            response_status=exc.response.status_code,
            response_text=detail,
        ) from exc
    except httpx.HTTPError as exc:
        raise PromptWorkflowError(
            f"Workflow request failed: {exc}",
            operation=operation,
            url=url,
            request_payload=request_payload,
        ) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise PromptWorkflowError(
            "Workflow response must be valid JSON.",
            operation=operation,
            url=url,
            request_payload=request_payload,
            response_status=response.status_code,
            response_text=response.text,
        ) from exc
    if not isinstance(payload, dict):
        raise PromptWorkflowError(
            "Workflow response must be a JSON object.",
            operation=operation,
            url=url,
            request_payload=request_payload,
            response_status=response.status_code,
            response_text=response.text,
        )
    return payload


def _should_retry_template_init(exc: PromptWorkflowError) -> bool:
    if exc.response_status in INIT_RETRYABLE_STATUS_CODES:
        return True
    detail = f"{exc} {exc.response_text or ''}".lower()
    return "markedtext does not render back to the original prompt exactly" in detail


def initialize_prompt_template(*, item_id: str, title: str, model: str, source_language: str, raw_text: str) -> dict[str, Any]:
    payload = {
        "item": {
            "id": item_id,
            "title": title,
            "model": model,
        },
        "prompt": {
            "language": source_language,
            "text": raw_text,
        },
    }
    url = _workflow_url(INIT_URL_ENV)

    last_error: PromptWorkflowError | None = None
    for attempt in range(1, INIT_MAX_ATTEMPTS + 1):
        try:
            response = _post_json(url, payload, operation="template_init")
            marked_text = response.get("markedText") or response.get("marked_text")
            if not isinstance(marked_text, str) or not marked_text.strip():
                raise PromptWorkflowError("Init workflow must return a non-empty markedText string.")
            return {
                "marked_text": marked_text,
                "analysis_confidence": response.get("confidence") or response.get("analysisConfidence"),
                "analysis_notes": response.get("notes") or response.get("analysisNotes"),
                "source_language": response.get("sourceLanguage") or response.get("source_language") or source_language,
            }
        except PromptWorkflowError as exc:
            last_error = exc
            if attempt >= INIT_MAX_ATTEMPTS or not _should_retry_template_init(exc):
                raise

    if last_error is not None:
        raise last_error
    raise PromptWorkflowError("Init workflow failed before producing a result.")


def generate_prompt_variant(*, template: PromptTemplateRecord, theme_keyword: str, previous_variants: list[PromptGenerationVariantRecord]) -> dict[str, Any]:
    payload = {
        "template": {
            "id": template.id,
            "itemId": template.item_id,
            "sourceLanguage": template.source_language,
            "rawText": template.raw_text_snapshot,
            "markedText": template.marked_text,
            "slots": [slot.model_dump() for slot in template.slots],
        },
        "themeKeyword": theme_keyword,
        "previousVariants": [
            {
                "id": variant.id,
                "iteration": variant.iteration,
                "renderedText": variant.rendered_text,
                "slotValues": [value.model_dump() for value in variant.slot_values],
                "changeSummary": variant.change_summary,
            }
            for variant in previous_variants
        ],
    }
    response = _post_json(_workflow_url(GENERATE_URL_ENV), payload, operation="template_generate")
    slot_values = response.get("slotValues") or response.get("slot_values")
    if not isinstance(slot_values, list) or not slot_values:
        raise PromptWorkflowError("Generate workflow must return a non-empty slotValues list.")
    return {
        "slot_values": slot_values,
        "change_summary": response.get("changeSummary") or response.get("change_summary") or response.get("notes"),
    }

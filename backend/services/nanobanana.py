from __future__ import annotations

import os
import time
from typing import Any, Callable

import httpx

from backend.schemas import NanobananaArticleImagesRequest

BASE_URL_ENV = "NANOBANANA_IMAGE_API_BASE_URL"
TOKEN_ENV = "NANOBANANA_IMAGE_API_TOKEN"
CALLBACK_URL_ENV = "NANOBANANA_IMAGE_CALLBACK_URL"
DEFAULT_BASE_URL = "https://image-api.wendealai.com"
TERMINAL_SUCCESS_STATUSES = {"completed", "partial_failed"}
TERMINAL_FAILURE_STATUSES = {"failed"}


class NanobananaUnavailable(RuntimeError):
    pass


class NanobananaError(RuntimeError):
    pass


class NanobananaBatchFailed(NanobananaError):
    pass


class NanobananaTimeout(NanobananaError):
    pass


def base_url() -> str:
    return os.environ.get(BASE_URL_ENV, DEFAULT_BASE_URL).strip().rstrip("/") or DEFAULT_BASE_URL


def callback_url() -> str | None:
    value = os.environ.get(CALLBACK_URL_ENV, "").strip()
    return value or None


def token() -> str:
    value = os.environ.get(TOKEN_ENV, "").strip()
    if not value:
        raise NanobananaUnavailable(f"{TOKEN_ENV} is not configured.")
    return value


def _auth_headers(api_token: str, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _json_response(response: httpx.Response) -> dict[str, Any]:
    text = response.text
    try:
        payload = response.json() if text else {}
    except ValueError as exc:
        raise NanobananaError("Nanobanana response must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise NanobananaError("Nanobanana response must be a JSON object.")
    if response.is_error:
        raise NanobananaError(f"Nanobanana HTTP {response.status_code}: {payload}")
    return payload


def _client_request(
    client: httpx.Client | None,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    try:
        if client is None:
            with httpx.Client(timeout=timeout) as owned_client:
                response = owned_client.request(method, url, headers=headers, json=json_body)
        else:
            response = client.request(method, url, headers=headers, json=json_body, timeout=timeout)
    except httpx.HTTPError as exc:
        raise NanobananaError(f"Nanobanana request failed: {exc}") from exc
    return _json_response(response)


def request_article_images(
    payload: NanobananaArticleImagesRequest,
    *,
    api_base_url: str | None = None,
    api_token: str | None = None,
    client: httpx.Client | None = None,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    resolved_token = api_token or token()
    resolved_base_url = (api_base_url or base_url()).rstrip("/")
    body = payload.model_dump(
        by_alias=True,
        exclude_none=True,
        exclude={"wait", "timeout_ms", "poll_interval_ms", "idempotency_key"},
    )
    if "callbackUrl" not in body:
        configured_callback_url = callback_url()
        if configured_callback_url:
            body["callbackUrl"] = configured_callback_url
    return _client_request(
        client,
        "POST",
        f"{resolved_base_url}/v1/article-images",
        headers=_auth_headers(resolved_token, payload.idempotency_key),
        json_body=body,
        timeout=timeout_seconds,
    )


def query_article_images(
    batch_id: str,
    *,
    status_url: str | None = None,
    api_base_url: str | None = None,
    api_token: str | None = None,
    client: httpx.Client | None = None,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    resolved_token = api_token or token()
    resolved_base_url = (api_base_url or base_url()).rstrip("/")
    url = status_url or f"{resolved_base_url}/v1/article-images/{batch_id}"
    return _client_request(
        client,
        "GET",
        url,
        headers=_auth_headers(resolved_token),
        timeout=timeout_seconds,
    )


def wait_for_article_images(
    *,
    batch_id: str,
    status_url: str | None = None,
    api_base_url: str | None = None,
    api_token: str | None = None,
    client: httpx.Client | None = None,
    timeout_ms: int = 15 * 60 * 1000,
    poll_interval_ms: int = 3000,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    started_at = now()
    timeout_seconds = timeout_ms / 1000
    poll_seconds = poll_interval_ms / 1000
    last_payload: dict[str, Any] | None = None

    while now() - started_at <= timeout_seconds:
        payload = query_article_images(
            batch_id,
            status_url=status_url,
            api_base_url=api_base_url,
            api_token=api_token,
            client=client,
        )
        last_payload = payload
        status = str((payload.get("batch") or {}).get("status") or "")
        if status in TERMINAL_SUCCESS_STATUSES:
            return payload
        if status in TERMINAL_FAILURE_STATUSES:
            raise NanobananaBatchFailed(f"Nanobanana batch failed: {payload}")
        sleep(poll_seconds)

    raise NanobananaTimeout(f"Nanobanana batch timed out. Last payload: {last_payload}")


def map_assets_by_slot(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    images = payload.get("images") or []
    if not isinstance(images, list):
        return mapped
    for image in images:
        if not isinstance(image, dict):
            continue
        slot = image.get("slot")
        if not isinstance(slot, str) or not slot:
            continue
        assets = image.get("assets") if isinstance(image.get("assets"), list) else []
        first_asset = assets[0] if assets and isinstance(assets[0], dict) else None
        mapped[slot] = {
            "status": image.get("status"),
            "itemId": image.get("itemId"),
            "assets": assets,
            "url": first_asset.get("url") if first_asset else None,
            "key": first_asset.get("key") if first_asset else None,
            "assetId": first_asset.get("assetId") if first_asset else None,
            "error": image.get("error"),
        }
    return mapped

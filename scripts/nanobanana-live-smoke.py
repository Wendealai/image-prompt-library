#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.schemas import NanobananaArticleImagesRequest, NanobananaImageRequest
from backend.services.nanobanana import TOKEN_ENV, base_url, request_article_images, wait_for_article_images


def _first_completed_asset(payload: dict[str, Any]) -> dict[str, Any]:
    for image in payload.get("images") or []:
        if not isinstance(image, dict) or image.get("status") != "completed":
            continue
        assets = image.get("assets") if isinstance(image.get("assets"), list) else []
        for asset in assets:
            if isinstance(asset, dict) and isinstance(asset.get("url"), str):
                return asset
    raise SystemExit("Live smoke did not receive a completed image asset.")


def _manifest_url(payload: dict[str, Any], batch_id: str) -> str:
    batch = payload.get("batch") if isinstance(payload.get("batch"), dict) else {}
    manifest_asset = batch.get("manifestAsset") if isinstance(batch.get("manifestAsset"), dict) else {}
    url = manifest_asset.get("url")
    if isinstance(url, str) and url:
        return url
    return f"{base_url()}/v1/article-images/{batch_id}/manifest"


def _assert_fetchable(client: httpx.Client, url: str, token: str) -> int:
    response = client.get(url)
    if response.status_code in {401, 403}:
        response = client.get(url, headers={"Authorization": f"Bearer {token}"})
    response.raise_for_status()
    return response.status_code


def main() -> None:
    api_token = os.environ.get(TOKEN_ENV, "").strip()
    if not api_token:
        raise SystemExit(f"{TOKEN_ENV} is not configured; set it before running the live smoke.")

    article_id = f"image-prompt-library-smoke-{int(time.time())}"
    payload = NanobananaArticleImagesRequest(
        articleId=article_id,
        projectId="image-prompt-library",
        idempotencyKey=f"{article_id}:nanobanana-live-smoke:v1",
        images=[
            NanobananaImageRequest(
                id="smoke",
                slot="smoke",
                prompt="A small neutral test image of a single yellow banana on a plain white background, clean studio lighting.",
            )
        ],
        wait=True,
        timeoutMs=15 * 60 * 1000,
        pollIntervalMs=3000,
        metadata={"sourceWorkflow": "image-prompt-library-live-smoke"},
    )

    with httpx.Client(timeout=60.0) as client:
        create_payload = request_article_images(payload, client=client)
        batch_id = str(create_payload.get("batchId") or "")
        if not batch_id:
            raise SystemExit(f"Create response did not include batchId: {create_payload}")
        terminal_payload = wait_for_article_images(
            batch_id=batch_id,
            status_url=create_payload.get("statusUrl") if isinstance(create_payload.get("statusUrl"), str) else None,
            client=client,
            timeout_ms=payload.timeout_ms,
            poll_interval_ms=payload.poll_interval_ms,
        )
        asset = _first_completed_asset(terminal_payload)
        manifest_url = _manifest_url(terminal_payload, batch_id)
        asset_status = _assert_fetchable(client, asset["url"], api_token)
        manifest_status = _assert_fetchable(client, manifest_url, api_token)

    print(json.dumps({
        "ok": True,
        "batchId": batch_id,
        "assetUrl": asset["url"],
        "assetStatus": asset_status,
        "manifestUrl": manifest_url,
        "manifestStatus": manifest_status,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Import a public X/Twitter prompt from a local manifest.

The manifest is intentionally local-file based so browser-only sources can be
captured with the Codex in-app browser, reviewed, then imported deterministically.
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.repositories import ItemRepository, StoredImageInput, now
from backend.schemas import ItemCreate, PromptIn
from backend.services.image_store import store_image
from backend.services.prompt_markup import validate_marked_prompt


def _library_path(configured: str | None) -> Path:
    if configured:
        return Path(configured).expanduser().resolve()
    return ROOT / "library"


def _read_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("Manifest must be a JSON object.")
    return data


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"Manifest field `{key}` is required.")
    return value.strip()


def _optional_text(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SystemExit(f"Manifest field `{field}` must be a list of strings.")
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _detect_suffix(content_type: str | None, fallback_name: str | None) -> str:
    if content_type:
        guess = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if guess:
            return ".jpg" if guess == ".jpe" else guess
    if fallback_name:
        suffix = Path(fallback_name).suffix
        if suffix:
            return suffix
    return ".jpg"


def _bytes_from_data_url(data_url: str) -> tuple[bytes, str | None]:
    match = re.match(r"data:([^;]+);base64,(.*)$", data_url, re.S)
    if not match:
        raise SystemExit("Image data_url must use data:<mime>;base64,... format.")
    content_type, payload = match.groups()
    return base64.b64decode(payload), content_type


def _bytes_from_image_entry(entry: dict[str, Any], manifest_dir: Path) -> tuple[bytes, str | None, str | None]:
    if isinstance(entry.get("data_url"), str):
        data, content_type = _bytes_from_data_url(entry["data_url"])
        return data, content_type, entry.get("filename") if isinstance(entry.get("filename"), str) else None
    if isinstance(entry.get("base64"), str):
        content_type = entry.get("content_type") if isinstance(entry.get("content_type"), str) else None
        filename = entry.get("filename") if isinstance(entry.get("filename"), str) else None
        return base64.b64decode(entry["base64"]), content_type, filename
    if isinstance(entry.get("path"), str):
        image_path = Path(entry["path"])
        if not image_path.is_absolute():
            image_path = manifest_dir / image_path
        content_type = entry.get("content_type") if isinstance(entry.get("content_type"), str) else None
        return image_path.read_bytes(), content_type, image_path.name
    image_url = entry.get("image_url") or entry.get("url")
    if isinstance(image_url, str) and image_url.strip().startswith(("http://", "https://")):
        with urlopen(image_url.strip(), timeout=30) as response:
            content_type = response.headers.get("content-type")
            filename = entry.get("filename") if isinstance(entry.get("filename"), str) else Path(image_url).name
            return response.read(), content_type, filename
    raise SystemExit("Each image needs one of `data_url`, `base64`, `path`, `image_url`, or `url`.")


def _duplicate_item(library_path: Path, source_url: str) -> dict[str, str] | None:
    db_path = library_path / "db.sqlite"
    if not db_path.exists():
        return None
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT
                items.id,
                items.title,
                COUNT(DISTINCT images.id) AS image_count,
                COUNT(DISTINCT prompt_templates.id) AS template_count
            FROM items
            LEFT JOIN images ON images.item_id = items.id
            LEFT JOIN prompt_templates ON prompt_templates.item_id = items.id
            WHERE items.source_url=? AND items.archived=0
            GROUP BY items.id, items.title
            """,
            (source_url,),
        ).fetchone()
    return dict(row) if row else None


def _notes(data: dict[str, Any], source_url: str, author: str | None) -> str:
    parts = [f"Original X status: {source_url}"]
    if author:
        parts.append(f"Author: {author}")
    for label, key in (
        ("Prompt reply", "prompt_reply_url"),
        ("Referenced earlier template", "quote_url"),
    ):
        value = _optional_text(data, key)
        if value:
            parts.append(f"{label}: {value}")
    intro = _optional_text(data, "tweet_intro")
    if intro:
        parts.append(f"Original tweet intro:\n{intro}")
    extra = _optional_text(data, "notes")
    if extra:
        parts.append(extra)
    return "\n\n".join(parts)


def _optional_float(data: dict[str, Any], key: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"Manifest field `{key}` must be a number.") from exc


def _save_prompt_template_if_present(
    *,
    repo: ItemRepository,
    item_id: str,
    prompt_text: str,
    prompt_language: str,
    data: dict[str, Any],
) -> str | None:
    raw_template = data.get("prompt_template")
    if raw_template is None:
        return None
    if not isinstance(raw_template, dict):
        raise SystemExit("Manifest field `prompt_template` must be an object.")

    marked_text = _required_text(raw_template, "marked_text")
    slots = validate_marked_prompt(prompt_text.strip(), marked_text)
    status = _optional_text(raw_template, "status") or "ready"
    review_status = _optional_text(raw_template, "review_status") or "pending_review"
    if status not in {"draft", "ready", "stale", "failed"}:
        raise SystemExit("Manifest field `prompt_template.status` must be draft, ready, stale, or failed.")
    if review_status not in {"pending_review", "approved", "rejected"}:
        raise SystemExit("Manifest field `prompt_template.review_status` must be pending_review, approved, or rejected.")

    reviewed_at = None
    if review_status in {"approved", "rejected"}:
        reviewed_at = now()

    template = repo.save_prompt_template(
        item_id=item_id,
        source_language=_optional_text(raw_template, "source_language") or prompt_language,
        raw_text_snapshot=prompt_text.strip(),
        marked_text=marked_text,
        slots=slots,
        status=status,
        review_status=review_status,
        review_notes=_optional_text(raw_template, "review_notes"),
        reviewed_at=reviewed_at,
        analysis_confidence=_optional_float(raw_template, "analysis_confidence"),
        analysis_notes=_optional_text(raw_template, "analysis_notes"),
    )
    return template.id


def import_manifest(manifest_path: Path, library_path: Path) -> dict[str, Any]:
    data = _read_manifest(manifest_path)
    source_url = _required_text(data, "source_url")
    existing = _duplicate_item(library_path, source_url)
    raw_template = data.get("prompt_template")
    if existing and existing["image_count"] and (raw_template is None or existing["template_count"]):
        return {
            "status": "exists",
            "item_id": existing["id"],
            "title": existing["title"],
            "image_count": existing["image_count"],
        }

    images = data.get("images")
    if not isinstance(images, list) or not images:
        raise SystemExit("Manifest field `images` must contain at least one image.")

    title = _required_text(data, "title")
    prompt_text = _required_text(data, "prompt_text")
    author = _optional_text(data, "author")
    prompt_language = _optional_text(data, "prompt_language") or "zh_hans"
    model = _optional_text(data, "model") or "ChatGPT Image2"
    source_name = _optional_text(data, "source_name") or "X / Twitter"
    slug_prefix = _optional_text(data, "image_filename_prefix") or re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-") or "x-prompt"

    repo = ItemRepository(library_path)
    item_id = existing["id"] if existing else None
    item_title = existing["title"] if existing else title
    if item_id is None:
        item = repo.create_item(
            ItemCreate(
                title=title,
                model=model,
                media_type=_optional_text(data, "media_type") or "image",
                source_name=source_name,
                source_url=source_url,
                author=author,
                cluster_name=_optional_text(data, "cluster_name"),
                rating=int(data.get("rating") or 0),
                favorite=bool(data.get("favorite") or False),
                notes=_notes(data, source_url, author),
                tags=_string_list(data.get("tags"), "tags"),
                prompts=[PromptIn(language=prompt_language, text=prompt_text, is_primary=True)],
            ),
            imported=True,
        )
        item_id = item.id
        item_title = item.title

    image_ids = []
    if not existing or not existing["image_count"]:
        for index, raw_entry in enumerate(images, start=1):
            if not isinstance(raw_entry, dict):
                raise SystemExit("Each image entry must be an object.")
            image_bytes, content_type, fallback_name = _bytes_from_image_entry(raw_entry, manifest_path.parent)
            filename = raw_entry.get("filename") if isinstance(raw_entry.get("filename"), str) else None
            if not filename:
                filename = f"{slug_prefix}-{index}{_detect_suffix(content_type, fallback_name)}"
            stored = store_image(library_path, image_bytes, filename)
            record = repo.add_image(
                item_id,
                StoredImageInput(
                    original_path=stored.original_path,
                    thumb_path=stored.thumb_path,
                    preview_path=stored.preview_path,
                    width=stored.width,
                    height=stored.height,
                    file_sha256=stored.file_sha256,
                    role=raw_entry.get("role") if raw_entry.get("role") in {"result_image", "reference_image"} else "result_image",
                ),
            )
            image_ids.append(record.id)

    template_id = None
    if not existing or not existing["template_count"]:
        template_id = _save_prompt_template_if_present(
            repo=repo,
            item_id=item_id,
            prompt_text=prompt_text,
            prompt_language=prompt_language,
            data=data,
        )

    return {
        "status": "updated_partial" if existing else "created",
        "item_id": item_id,
        "title": item_title,
        "image_count": len(image_ids) if image_ids else existing["image_count"] if existing else 0,
        "template_id": template_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON manifest with source_url, title, prompt_text, tags, and images")
    parser.add_argument("--library", help="Library path. Defaults to IMAGE_PROMPT_LIBRARY_PATH or ./library")
    parser.add_argument("--after-import", action="store_true", help="Run scripts/after-import.py after creating a new item")
    args = parser.parse_args()

    library_path = _library_path(args.library)
    result = import_manifest(args.manifest.resolve(), library_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.after_import and result["status"] == "created":
        subprocess.run([sys.executable, "scripts/after-import.py"], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

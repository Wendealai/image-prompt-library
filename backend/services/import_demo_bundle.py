from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

from backend.db import connect, init_db
from backend.repositories import ItemRepository, StoredImageInput, new_id, now
from backend.schemas import ImportResult, ItemCreate, PromptIn
from backend.services.image_store import store_image
from backend.services.import_sample_bundle import _already_imported, _clean_text, _replace_prompts_exactly

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUNDLE_PATH = ROOT / "frontend" / "public" / "demo-data"
DEFAULT_PUBLIC_V0_1_BUNDLE_URL = "https://eddietyp.github.io/image-prompt-library/v0.1/demo-data"


def _is_remote_bundle(source: str | Path) -> bool:
    return isinstance(source, str) and urlparse(source).scheme in {"http", "https"}


def _normalize_asset_path(value: str) -> str:
    normalized = value.lstrip("./")
    if normalized.startswith("demo-data/"):
        return normalized[len("demo-data/") :]
    return normalized


def _load_json(source: str | Path, name: str) -> Any:
    if _is_remote_bundle(source):
        base_url = f"{str(source).rstrip('/')}/"
        with urlopen(urljoin(base_url, name)) as response:
            return json.loads(response.read().decode("utf-8"))
    bundle_path = Path(source)
    return json.loads((bundle_path / name).read_text(encoding="utf-8"))


def _load_asset_bytes(source: str | Path, value: str) -> tuple[bytes, str]:
    normalized = _normalize_asset_path(value)
    filename = Path(normalized).name or "image.webp"
    if _is_remote_bundle(source):
        base_url = f"{str(source).rstrip('/')}/"
        with urlopen(urljoin(base_url, normalized)) as response:
            return response.read(), filename
    bundle_path = Path(source)
    asset_path = (bundle_path / normalized).resolve()
    try:
        asset_path.relative_to(bundle_path.resolve())
    except ValueError as exc:
        raise ValueError(f"Asset path escapes bundle root: {value}") from exc
    return asset_path.read_bytes(), filename


def _prompt_records(item: dict[str, Any]) -> list[PromptIn]:
    prompts: list[PromptIn] = []
    for index, prompt in enumerate(item.get("prompts", [])):
        if not isinstance(prompt, dict):
            continue
        language = _clean_text(prompt.get("language")) or "en"
        text = _clean_text(prompt.get("text"))
        if not text:
            continue
        prompts.append(PromptIn(language=language, text=text, is_primary=bool(prompt.get("is_primary", index == 0))))
    if prompts and not any(prompt.is_primary for prompt in prompts):
        prompts[0].is_primary = True
    return prompts


def _tag_names(item: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for tag in item.get("tags", []):
        name = _clean_text(tag.get("name")) if isinstance(tag, dict) else _clean_text(tag)
        if name:
            names.append(name)
    return list(dict.fromkeys(names))


def _cluster_name(item: dict[str, Any]) -> str | None:
    cluster = item.get("cluster")
    if isinstance(cluster, dict):
        return _clean_text(cluster.get("name"))
    return None


def _image_records(item: dict[str, Any]) -> list[dict[str, Any]]:
    images = [image for image in item.get("images", []) if isinstance(image, dict)]
    if images:
        return images
    first_image = item.get("first_image")
    return [first_image] if isinstance(first_image, dict) else []


def _id_available(library_path: Path, item_id: str | None) -> bool:
    if not item_id:
        return False
    with connect(library_path) as conn:
        return conn.execute("SELECT 1 FROM items WHERE id=?", (item_id,)).fetchone() is None


def import_demo_bundle(bundle: str | Path = DEFAULT_BUNDLE_PATH, library: str | Path = "library") -> ImportResult:
    library_path = Path(library)
    init_db(library_path)
    repo = ItemRepository(library_path)
    items = _load_json(bundle, "items.json")
    if not isinstance(items, list):
        raise ValueError("Demo bundle items.json must contain a list")

    batch_id = new_id("imp")
    started = now()
    item_count = 0
    image_count = 0
    log: list[str] = []

    with connect(library_path) as conn:
        conn.execute(
            "INSERT INTO imports(id,source_name,source_path,status,started_at,log) VALUES(?,?,?,?,?,?)",
            (batch_id, "demo-data", str(bundle), "running", started, ""),
        )
        conn.commit()

    for item in items:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title")) or "Untitled demo item"
        slug = _clean_text(item.get("slug")) or _clean_text(item.get("id")) or title
        if _already_imported(library_path, slug):
            continue

        prompts = _prompt_records(item)
        created = repo.create_item(
            ItemCreate(
                title=title,
                slug=slug,
                model=_clean_text(item.get("model")) or "Image Prompt Library demo",
                cluster_name=_cluster_name(item),
                tags=_tag_names(item),
                prompts=prompts,
                source_name=_clean_text(item.get("source_name")),
                source_url=_clean_text(item.get("source_url")),
                author=_clean_text(item.get("author")),
                notes=_clean_text(item.get("notes")),
                rating=int(item.get("rating") or 0),
                favorite=bool(item.get("favorite")),
                archived=bool(item.get("archived")),
            ),
            imported=True,
            forced_id=_clean_text(item.get("id")) if _id_available(library_path, _clean_text(item.get("id"))) else None,
        )
        if prompts:
            _replace_prompts_exactly(library_path, repo, created.id, prompts)
        item_count += 1

        for image in _image_records(item):
            image_ref = (
                _clean_text(image.get("original_path"))
                or _clean_text(image.get("preview_path"))
                or _clean_text(image.get("thumb_path"))
            )
            if not image_ref:
                log.append(f"Missing image path for {slug}")
                continue
            try:
                data, filename = _load_asset_bytes(bundle, image_ref)
            except Exception as exc:
                log.append(f"Failed to load image for {slug}: {image_ref} ({exc})")
                continue
            stored = store_image(library_path, data, filename)
            role = _clean_text(image.get("role")) or "result_image"
            if role not in {"result_image", "reference_image"}:
                role = "result_image"
            repo.add_image(
                created.id,
                StoredImageInput(
                    original_path=stored.original_path,
                    thumb_path=stored.thumb_path,
                    preview_path=stored.preview_path,
                    width=stored.width,
                    height=stored.height,
                    file_sha256=stored.file_sha256,
                    role=role,
                ),
            )
            image_count += 1

    with connect(library_path) as conn:
        conn.execute(
            "UPDATE imports SET status=?, item_count=?, image_count=?, finished_at=?, log=? WHERE id=?",
            ("completed", item_count, image_count, now(), "\n".join(log), batch_id),
        )
        conn.commit()

    return ImportResult(id=batch_id, item_count=item_count, image_count=image_count, status="completed", log="\n".join(log))


def main() -> None:
    parser = argparse.ArgumentParser(description="Import the public Image Prompt Library demo bundle into a local library.")
    parser.add_argument("--bundle", default=str(DEFAULT_BUNDLE_PATH), help="Local demo bundle directory or remote demo-data base URL")
    parser.add_argument("--library", default="library", help="Image Prompt Library data path")
    parser.add_argument(
        "--public-v0.1",
        dest="public_v0_1",
        action="store_true",
        help="Import the archived v0.1 public demo bundle from GitHub Pages",
    )
    args = parser.parse_args()
    bundle = DEFAULT_PUBLIC_V0_1_BUNDLE_URL if args.public_v0_1 else args.bundle
    print(import_demo_bundle(bundle=bundle, library=args.library).model_dump_json(indent=2))


if __name__ == "__main__":
    main()

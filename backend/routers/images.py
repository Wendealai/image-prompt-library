from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from PIL import UnidentifiedImageError
from backend.repositories import ItemRepository, StoredImageInput
from backend.schemas import ImageRecord, ItemDetail
from backend.services.image_store import store_image
router = APIRouter()

MAX_UPLOAD_BYTES = 30 * 1024 * 1024
IMAGE_MEDIA_TYPES = {
    ".gif": "image/gif",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _image_file_paths(image: ImageRecord) -> list[str]:
    return [path for path in (image.original_path, image.preview_path, image.thumb_path) if path]


def _delete_unreferenced_image_files(library_path: Path | str, image: ImageRecord, paths_in_use: set[str]):
    library = Path(library_path).resolve()
    for rel_path in _image_file_paths(image):
        if rel_path in paths_in_use:
            continue
        clean_path = rel_path.strip()
        if not clean_path or clean_path.startswith(("http://", "https://", "data:", "blob:")):
            continue
        try:
            candidate = Path(clean_path)
            path = (candidate if candidate.is_absolute() else library / candidate).resolve()
            path.relative_to(library)
        except (OSError, RuntimeError, ValueError):
            continue
        if path == library:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _attachment_filename(image: ImageRecord) -> str:
    source = image.original_path or image.remote_url or image.preview_path or image.thumb_path or ""
    suffix = Path(urlparse(source).path).suffix.lower()
    if suffix not in IMAGE_MEDIA_TYPES:
        suffix = ".jpg"
    return f"{image.id}{suffix}"


def _resolve_local_original(library_path: Path | str, image: ImageRecord) -> Path | None:
    source = (image.original_path or "").strip()
    if not source or source.startswith(("http://", "https://", "data:", "blob:")):
        return None
    library = Path(library_path).resolve()
    try:
        candidate = (Path(source) if Path(source).is_absolute() else library / source).resolve()
        candidate.relative_to(library)
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate if candidate.is_file() else None


def _remote_original_url(image: ImageRecord) -> str:
    for source in (image.remote_url, image.original_path):
        clean = (source or "").strip()
        if clean.startswith(("http://", "https://")):
            return clean
    return ""

@router.post("/items/{item_id}/images")
async def upload_image(request: Request, item_id: str, file: UploadFile = File(...), role: str = Form("result_image")):
    if role not in {"result_image", "reference_image"}:
        raise HTTPException(400, "Invalid image role")
    repository = ItemRepository(request.app.state.library_path)
    try:
        repository.get_item(item_id)
    except KeyError as exc:
        raise HTTPException(404, "Item not found") from exc
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image upload too large")
    try:
        stored = store_image(request.app.state.library_path, data, file.filename or "image.png")
    except (ValueError, UnidentifiedImageError) as exc:
        raise HTTPException(400, str(exc)) from exc
    rec = repository.add_image(item_id, StoredImageInput(stored.original_path, stored.thumb_path, stored.preview_path, width=stored.width, height=stored.height, file_sha256=stored.file_sha256, role=role))
    return rec


@router.delete("/items/{item_id}/images/{image_id}", response_model=ItemDetail)
def delete_image(request: Request, item_id: str, image_id: str):
    repository = ItemRepository(request.app.state.library_path)
    try:
        deleted = repository.delete_image(item_id, image_id)
    except KeyError as exc:
        raise HTTPException(404, "Image not found") from exc
    paths_in_use = repository.image_paths_in_use(_image_file_paths(deleted))
    _delete_unreferenced_image_files(request.app.state.library_path, deleted, paths_in_use)
    return repository.get_item(item_id)


@router.get("/items/{item_id}/images/{image_id}/download")
def download_image(request: Request, item_id: str, image_id: str):
    repository = ItemRepository(request.app.state.library_path)
    try:
        item = repository.get_item(item_id)
    except KeyError as exc:
        raise HTTPException(404, "Item not found") from exc
    image = next((candidate for candidate in item.images if candidate.id == image_id), None)
    if image is None:
        raise HTTPException(404, "Image not found")
    filename = _attachment_filename(image)
    local_original = _resolve_local_original(request.app.state.library_path, image)
    if local_original:
        return FileResponse(
            local_original,
            media_type=IMAGE_MEDIA_TYPES.get(local_original.suffix.lower(), "application/octet-stream"),
            filename=filename,
        )
    remote_url = _remote_original_url(image)
    if not remote_url:
        raise HTTPException(404, "Original image not found")
    try:
        remote_response = httpx.get(remote_url, follow_redirects=True, timeout=30.0)
        remote_response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Remote original image could not be downloaded") from exc
    return Response(
        content=remote_response.content,
        media_type=remote_response.headers.get("content-type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

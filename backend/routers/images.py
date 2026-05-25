from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from PIL import UnidentifiedImageError
from backend.repositories import ItemRepository, StoredImageInput
from backend.schemas import ImageRecord, ItemDetail
from backend.services.image_store import store_image
router = APIRouter()

MAX_UPLOAD_BYTES = 30 * 1024 * 1024


def _image_file_paths(image: ImageRecord) -> list[str]:
    return [path for path in (image.original_path, image.preview_path, image.thumb_path) if path]


def _delete_unreferenced_image_files(library_path: Path | str, image: ImageRecord, paths_in_use: set[str]):
    library = Path(library_path).resolve()
    for rel_path in _image_file_paths(image):
        if rel_path in paths_in_use:
            continue
        path = (library / rel_path).resolve()
        if library not in path.parents:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

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

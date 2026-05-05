from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
import httpx

from backend.admin_auth import has_admin_session, verify_admin_password
from backend.schemas import CangheGallerySyncRequest, CangheGallerySyncResponse, CaseIntakeFetchRequest, CaseIntakeFetchResult
from backend.services.case_intake import fetch_case_image_from_url, fetch_case_intake_from_url
from backend.services.canghe_gallery_sync import sync_canghe_gallery

router = APIRouter()


@router.post("/intake/fetch", response_model=CaseIntakeFetchResult)
def fetch_case_intake(payload: CaseIntakeFetchRequest):
    try:
        return fetch_case_intake_from_url(payload.url)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Failed to fetch the source URL.") from exc


@router.get("/intake/image")
def fetch_case_image(url: str):
    try:
        fetched = fetch_case_image_from_url(url)
        return Response(
            content=fetched.data,
            media_type=fetched.content_type,
            headers={"x-intake-filename": fetched.filename, "Cache-Control": "no-store"},
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Failed to fetch the source image.") from exc


@router.post("/admin/intake/canghe-gallery/sync", response_model=CangheGallerySyncResponse)
def sync_canghe_gallery_endpoint(request: Request, payload: CangheGallerySyncRequest):
    if not has_admin_session(request) and not (payload.admin_password and verify_admin_password(payload.admin_password)):
        raise HTTPException(status_code=401, detail="Admin authentication required.")
    try:
        return sync_canghe_gallery(
            request.app.state.library_path,
            dry_run=payload.dry_run,
            max_imports=payload.max_imports,
            initialize_templates=payload.initialize_templates,
            approve_templates=payload.approve_templates,
        )
    except ValueError as exc:
        raise HTTPException(502, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Failed to fetch Canghe gallery data.") from exc

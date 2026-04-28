from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
import httpx

from backend.schemas import CaseIntakeFetchRequest, CaseIntakeFetchResult
from backend.services.case_intake import fetch_case_image_from_url, fetch_case_intake_from_url

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

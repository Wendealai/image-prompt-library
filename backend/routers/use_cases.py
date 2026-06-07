from fastapi import APIRouter, Request

from backend.repositories import ItemRepository

router = APIRouter()


@router.get("/use-cases")
def use_cases(request: Request):
    return ItemRepository(request.app.state.library_path).list_use_cases()

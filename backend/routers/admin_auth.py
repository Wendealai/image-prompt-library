from fastapi import APIRouter, HTTPException, Request, Response

from backend.admin_auth import clear_admin_session_cookie, has_admin_session, set_admin_session_cookie, verify_admin_password
from backend.schemas import AdminLoginRequest, AdminSessionRecord

router = APIRouter()


@router.get("/admin/auth/session", response_model=AdminSessionRecord)
def get_admin_session(request: Request):
    return AdminSessionRecord(authenticated=has_admin_session(request))


@router.post("/admin/auth/login", response_model=AdminSessionRecord)
def login_admin(request: Request, response: Response, payload: AdminLoginRequest):
    if not verify_admin_password(payload.password):
        clear_admin_session_cookie(response, request)
        raise HTTPException(status_code=401, detail="Invalid admin password.")
    set_admin_session_cookie(response, request)
    return AdminSessionRecord(authenticated=True)


@router.post("/admin/auth/logout", response_model=AdminSessionRecord)
def logout_admin(request: Request, response: Response):
    clear_admin_session_cookie(response, request)
    return AdminSessionRecord(authenticated=False)

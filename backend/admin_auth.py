from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import HTTPException, Request, Response

from .config import get_admin_password, get_admin_session_secret

ADMIN_SESSION_COOKIE = "image_prompt_library_admin_session"
ADMIN_SESSION_MAX_AGE = 60 * 60 * 24 * 14
_ADMIN_SCOPE = "admin"
_ADMIN_VERSION = "v1"


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def _session_signature(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return _urlsafe_b64encode(digest)


def _session_payload(expires_at: int) -> str:
    encoded_scope = _urlsafe_b64encode(_ADMIN_SCOPE.encode("utf-8"))
    return f"{_ADMIN_VERSION}:{expires_at}:{encoded_scope}"


def _is_https_request(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    return request.url.scheme == "https" or forwarded == "https"


def verify_admin_password(password: str) -> bool:
    return hmac.compare_digest(password, get_admin_password())


def build_admin_session_token(request: Request) -> str:
    expires_at = int(time.time()) + ADMIN_SESSION_MAX_AGE
    payload = _session_payload(expires_at)
    signature = _session_signature(payload, get_admin_session_secret(request.app.state.library_path))
    return f"{payload}.{signature}"


def has_admin_session(request: Request) -> bool:
    token = request.cookies.get(ADMIN_SESSION_COOKIE)
    if not token:
        return False
    try:
        payload, signature = token.rsplit(".", 1)
        expected = _session_signature(payload, get_admin_session_secret(request.app.state.library_path))
        if not hmac.compare_digest(signature, expected):
            return False
        version, expires_at_raw, encoded_scope = payload.split(":", 2)
        if version != _ADMIN_VERSION:
            return False
        if int(expires_at_raw) < int(time.time()):
            return False
        if _urlsafe_b64decode(encoded_scope).decode("utf-8") != _ADMIN_SCOPE:
            return False
    except Exception:
        return False
    return True


def require_admin(request: Request) -> None:
    if not has_admin_session(request):
        raise HTTPException(status_code=401, detail="Admin authentication required.")


def set_admin_session_cookie(response: Response, request: Request) -> None:
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=build_admin_session_token(request),
        max_age=ADMIN_SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=_is_https_request(request),
        path="/",
    )


def clear_admin_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        key=ADMIN_SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_is_https_request(request),
    )

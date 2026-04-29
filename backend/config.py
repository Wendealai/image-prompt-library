import os
from pathlib import Path

APP_VERSION = "0.1.0"
DEFAULT_LIBRARY_PATH = Path(__file__).resolve().parents[1] / "library"
DEFAULT_ADMIN_PASSWORD = "zwyy0323"


def resolve_library_path(library_path=None) -> Path:
    configured_path = library_path if library_path is not None else os.environ.get("IMAGE_PROMPT_LIBRARY_PATH")
    path = Path(configured_path).expanduser() if configured_path is not None else DEFAULT_LIBRARY_PATH
    path.mkdir(parents=True, exist_ok=True)
    for child in ("originals", "thumbs", "previews"):
        (path / child).mkdir(parents=True, exist_ok=True)
    return path


def get_admin_password() -> str:
    return os.environ.get("IMAGE_PROMPT_LIBRARY_ADMIN_PASSWORD") or DEFAULT_ADMIN_PASSWORD


def get_admin_session_secret(library_path=None) -> str:
    configured = os.environ.get("IMAGE_PROMPT_LIBRARY_ADMIN_SESSION_SECRET")
    if configured:
        return configured
    library = resolve_library_path(library_path)
    return f"{get_admin_password()}::{APP_VERSION}::{library.resolve()}"

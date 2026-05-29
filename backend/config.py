import os
import secrets
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def get_app_version() -> str:
    try:
        return version("image-prompt-library")
    except PackageNotFoundError:
        return "0.1.0"


APP_VERSION = get_app_version()
DEFAULT_LIBRARY_PATH = Path(__file__).resolve().parents[1] / "library"
DEFAULT_ADMIN_PASSWORD = ""
DEFAULT_LINK_IMPORT_SKILL_URL = "https://x.com/MrDasOnX/status/2049527944905982314"


def resolve_library_path(library_path=None) -> Path:
    configured_path = library_path if library_path is not None else os.environ.get("IMAGE_PROMPT_LIBRARY_PATH")
    path = Path(configured_path).expanduser() if configured_path is not None else DEFAULT_LIBRARY_PATH
    path.mkdir(parents=True, exist_ok=True)
    for child in ("originals", "thumbs", "previews"):
        (path / child).mkdir(parents=True, exist_ok=True)
    return path


def get_admin_password() -> str:
    return os.environ.get("IMAGE_PROMPT_LIBRARY_ADMIN_PASSWORD", "").strip() or DEFAULT_ADMIN_PASSWORD


def get_admin_session_secret(library_path=None) -> str:
    configured = os.environ.get("IMAGE_PROMPT_LIBRARY_ADMIN_SESSION_SECRET")
    if configured:
        return configured
    library = resolve_library_path(library_path)
    secret_path = library / ".admin_session_secret"
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()
    secret = secrets.token_urlsafe(48)
    secret_path.write_text(secret, encoding="utf-8")
    return secret


def default_link_import_skill_url() -> str:
    return os.environ.get("IMAGE_PROMPT_LIBRARY_DEFAULT_IMPORT_SKILL_URL", DEFAULT_LINK_IMPORT_SKILL_URL).strip()

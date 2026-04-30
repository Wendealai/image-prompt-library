import os
from pathlib import Path

APP_VERSION = "0.1.0"
DEFAULT_LIBRARY_PATH = Path(__file__).resolve().parents[1] / "library"
DEFAULT_LINK_IMPORT_SKILL_URL = "https://x.com/MrDasOnX/status/2049527944905982314"


def resolve_library_path(library_path=None) -> Path:
    configured_path = library_path if library_path is not None else os.environ.get("IMAGE_PROMPT_LIBRARY_PATH")
    path = Path(configured_path).expanduser() if configured_path is not None else DEFAULT_LIBRARY_PATH
    path.mkdir(parents=True, exist_ok=True)
    for child in ("originals", "thumbs", "previews"):
        (path / child).mkdir(parents=True, exist_ok=True)
    return path


def default_link_import_skill_url() -> str:
    return os.environ.get("IMAGE_PROMPT_LIBRARY_DEFAULT_IMPORT_SKILL_URL", DEFAULT_LINK_IMPORT_SKILL_URL).strip()

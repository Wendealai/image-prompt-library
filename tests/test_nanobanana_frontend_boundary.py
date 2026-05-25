from __future__ import annotations

from pathlib import Path


def test_nanobanana_secrets_are_not_referenced_by_frontend_source():
    frontend_root = Path("frontend")
    searched_suffixes = {".css", ".html", ".js", ".jsx", ".json", ".ts", ".tsx"}
    forbidden = {
        "NANOBANANA_IMAGE_API_TOKEN",
        "Authorization: Bearer",
        "image-api.wendealai.com/v1/article-images",
    }
    offenders: list[str] = []

    for path in frontend_root.rglob("*"):
        if "node_modules" in path.parts or path.is_dir() or path.suffix not in searched_suffixes:
            continue
        content = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in content:
                offenders.append(f"{path}:{marker}")

    assert offenders == []

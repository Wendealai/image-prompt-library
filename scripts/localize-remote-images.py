#!/usr/bin/env python3
"""Download remote-only image records into the local library image store."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx

from backend.config import resolve_library_path
from backend.services.image_store import store_image


REMOTE_ONLY_SQL = """
SELECT id, remote_url, original_path, thumb_path, preview_path
FROM images
WHERE remote_url LIKE 'http%'
  AND (
    thumb_path IS NULL
    OR preview_path IS NULL
    OR original_path LIKE 'http%'
  )
ORDER BY created_at, sort_order
"""


def _filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name
    if "." not in name:
        return "remote-image.jpg"
    return name


def _candidate_urls(remote_url: str) -> list[str]:
    urls = [remote_url]
    parsed = urlparse(remote_url)
    if "/pic/orig/" in parsed.path:
        encoded = parsed.path.rsplit("/pic/orig/", 1)[-1]
        decoded = unquote(encoded)
        if decoded.startswith("media/"):
            urls.append(f"https://pbs.twimg.com/{decoded}")
    return urls


def localize_remote_images(library: Path, *, limit: int | None = None, dry_run: bool = False) -> dict[str, int]:
    stats = {"candidates": 0, "localized": 0, "failed": 0, "skipped": 0}
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ImagePromptLibrary/0.1; +https://prompt.wendealai.com)",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    timeout = httpx.Timeout(45.0, connect=15.0)
    with sqlite3.connect(library / "db.sqlite") as conn, httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(REMOTE_ONLY_SQL).fetchall()
        if limit is not None:
            rows = rows[:limit]
        stats["candidates"] = len(rows)
        for row in rows:
            image_id = row["id"]
            remote_url = row["remote_url"]
            if dry_run:
                print(f"DRY {image_id} {remote_url}")
                stats["skipped"] += 1
                continue
            try:
                last_exc: Exception | None = None
                response = None
                for candidate_url in _candidate_urls(remote_url):
                    try:
                        response = client.get(candidate_url)
                        response.raise_for_status()
                        break
                    except Exception as exc:
                        last_exc = exc
                        response = None
                if response is None:
                    raise last_exc or RuntimeError("image download failed")
                content_type = response.headers.get("content-type", "")
                if "image" not in content_type.lower():
                    raise ValueError(f"non-image response: {content_type or 'unknown content-type'}")
                stored = store_image(library, response.content, _filename_from_url(remote_url))
                conn.execute(
                    """
                    UPDATE images
                    SET original_path=?, thumb_path=?, preview_path=?, width=?, height=?, file_sha256=?
                    WHERE id=?
                    """,
                    (
                        stored.original_path,
                        stored.thumb_path,
                        stored.preview_path,
                        stored.width,
                        stored.height,
                        stored.file_sha256,
                        image_id,
                    ),
                )
                conn.commit()
                stats["localized"] += 1
                print(f"OK {image_id} {stored.width}x{stored.height} {remote_url}")
            except Exception as exc:
                stats["failed"] += 1
                print(f"FAIL {image_id} {remote_url} :: {exc}")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, default=resolve_library_path())
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stats = localize_remote_images(args.library, limit=args.limit, dry_run=args.dry_run)
    print(stats)
    if stats["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

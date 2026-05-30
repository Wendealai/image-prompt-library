#!/usr/bin/env python3
"""Check library and demo-export image/count health after imports."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO_ROOT = ROOT / "frontend" / "public" / "demo-data"


def _default_library_path() -> Path:
    configured = os.environ.get("IMAGE_PROMPT_LIBRARY_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return ROOT / "library"


def _is_remote_path(value: str | None) -> bool:
    return bool(value and value.startswith(("http://", "https://")))


def _local_image_exists(library_path: Path, value: str | None) -> bool:
    if not value or _is_remote_path(value):
        return False
    return (library_path / value).exists()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_demo_media_refs(value: Any, refs: set[str]) -> None:
    if isinstance(value, str) and value.startswith("demo-data/media/"):
        refs.add(value.rsplit("/", 1)[-1])
    elif isinstance(value, dict):
        for child in value.values():
            _collect_demo_media_refs(child, refs)
    elif isinstance(value, list):
        for child in value:
            _collect_demo_media_refs(child, refs)


@dataclass
class HealthIssue:
    code: str
    detail: str


@dataclass
class HealthReport:
    library_path: str
    demo_root: str
    active_count: int = 0
    image_count: int = 0
    demo_item_count: int = 0
    demo_cluster_count: int = 0
    demo_tag_count: int = 0
    demo_media_files: int = 0
    demo_media_references: int = 0
    missing_image_active: int = 0
    remote_only_images: int = 0
    missing_local_image_files: int = 0
    issues: list[HealthIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def to_json(self) -> str:
        payload = {
            "ok": self.ok,
            "library_path": self.library_path,
            "demo_root": self.demo_root,
            "active_count": self.active_count,
            "image_count": self.image_count,
            "demo_item_count": self.demo_item_count,
            "demo_cluster_count": self.demo_cluster_count,
            "demo_tag_count": self.demo_tag_count,
            "demo_media_files": self.demo_media_files,
            "demo_media_references": self.demo_media_references,
            "missing_image_active": self.missing_image_active,
            "remote_only_images": self.remote_only_images,
            "missing_local_image_files": self.missing_local_image_files,
            "issues": [issue.__dict__ for issue in self.issues],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


def check_library(library_path: Path, demo_root: Path) -> HealthReport:
    report = HealthReport(str(library_path), str(demo_root))
    db_path = library_path / "db.sqlite"
    if not db_path.exists():
        report.issues.append(HealthIssue("missing-db", f"Database not found: {db_path}"))
        return report

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        report.active_count = conn.execute("SELECT COUNT(*) FROM items WHERE archived=0").fetchone()[0]
        report.image_count = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
        missing_items = conn.execute(
            """
            SELECT id,title,source_url
            FROM items i
            WHERE i.archived=0
            AND NOT EXISTS (SELECT 1 FROM images img WHERE img.item_id=i.id)
            ORDER BY updated_at DESC
            """
        ).fetchall()
        remote_only = conn.execute(
            """
            SELECT id,item_id,remote_url
            FROM images
            WHERE remote_url IS NOT NULL
            AND (original_path IS NULL OR original_path=remote_url OR original_path LIKE 'http%')
            AND (thumb_path IS NULL OR thumb_path='')
            AND (preview_path IS NULL OR preview_path='')
            """
        ).fetchall()
        image_rows = conn.execute(
            """
            SELECT id,item_id,original_path,thumb_path,preview_path,remote_url
            FROM images
            ORDER BY created_at DESC
            """
        ).fetchall()

    report.missing_image_active = len(missing_items)
    report.remote_only_images = len(remote_only)
    if missing_items:
        titles = ", ".join(f"{row['title']} ({row['id']})" for row in missing_items[:8])
        report.issues.append(HealthIssue("active-items-without-images", titles))
    if remote_only:
        ids = ", ".join(f"{row['id']}:{row['item_id']}" for row in remote_only[:8])
        report.issues.append(HealthIssue("remote-only-images", ids))

    missing_local = []
    for row in image_rows:
        has_existing_local = any(
            _local_image_exists(library_path, row[key])
            for key in ("preview_path", "thumb_path", "original_path")
        )
        if not has_existing_local:
            missing_local.append(row)
    report.missing_local_image_files = len(missing_local)
    if missing_local:
        ids = ", ".join(f"{row['id']}:{row['item_id']}" for row in missing_local[:8])
        report.issues.append(HealthIssue("missing-local-image-files", ids))

    required_demo = ["items.json", "clusters.json", "tags.json", "metadata.json"]
    missing_demo_files = [name for name in required_demo if not (demo_root / name).exists()]
    if missing_demo_files:
        report.issues.append(HealthIssue("missing-demo-files", ", ".join(missing_demo_files)))
        return report

    items = _load_json(demo_root / "items.json")
    clusters = _load_json(demo_root / "clusters.json")
    tags = _load_json(demo_root / "tags.json")
    metadata = _load_json(demo_root / "metadata.json")
    media_files = {path.name for path in (demo_root / "media").glob("*.webp")}
    refs: set[str] = set()
    _collect_demo_media_refs(items, refs)
    _collect_demo_media_refs(clusters, refs)

    report.demo_item_count = len(items)
    report.demo_cluster_count = len(clusters)
    report.demo_tag_count = len(tags)
    report.demo_media_files = len(media_files)
    report.demo_media_references = len(refs)

    if metadata.get("item_count") != len(items):
        report.issues.append(
            HealthIssue("metadata-item-count-mismatch", f"{metadata.get('item_count')} != {len(items)}")
        )
    if len(items) != report.active_count:
        report.issues.append(HealthIssue("demo-db-item-count-mismatch", f"{len(items)} != {report.active_count}"))
    unresolved_refs = sorted(refs - media_files)
    if unresolved_refs:
        report.issues.append(HealthIssue("demo-media-references-missing-files", ", ".join(unresolved_refs[:8])))
    orphan_media = sorted(media_files - refs)
    if orphan_media:
        report.issues.append(HealthIssue("demo-media-files-unreferenced", ", ".join(orphan_media[:8])))

    image_less_demo = [
        item.get("slug") or item.get("id")
        for item in items
        if not item.get("first_image")
        or not any(item["first_image"].get(key) for key in ("thumb_path", "preview_path", "original_path"))
    ]
    if image_less_demo:
        report.issues.append(HealthIssue("demo-items-without-local-first-image", ", ".join(image_less_demo[:8])))

    remote_demo_images = []
    for item in items:
        for image in item.get("images", []):
            if image.get("remote_url") or any(_is_remote_path(image.get(key)) for key in ("original_path", "thumb_path", "preview_path")):
                remote_demo_images.append(f"{item.get('slug')}:{image.get('id')}")
    if remote_demo_images:
        report.issues.append(HealthIssue("demo-images-still-remote", ", ".join(remote_demo_images[:8])))

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=_default_library_path())
    parser.add_argument("--demo-root", type=Path, default=DEFAULT_DEMO_ROOT)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    report = check_library(args.library.resolve(), args.demo_root.resolve())
    if args.json:
        print(report.to_json())
    else:
        status = "ok" if report.ok else "failed"
        print(f"Library health: {status}")
        print(
            "Counts: "
            f"active={report.active_count}, demo={report.demo_item_count}, "
            f"clusters={report.demo_cluster_count}, tags={report.demo_tag_count}, "
            f"media={report.demo_media_files}, referenced={report.demo_media_references}"
        )
        print(
            "Images: "
            f"missing_active={report.missing_image_active}, "
            f"remote_only={report.remote_only_images}, "
            f"missing_local_files={report.missing_local_image_files}"
        )
        for issue in report.issues:
            print(f"- {issue.code}: {issue.detail}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

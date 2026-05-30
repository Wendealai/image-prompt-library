from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_package_exposes_post_import_maintenance_commands():
    package_json = (ROOT / "package.json").read_text(encoding="utf-8")
    assert '"after-import": "python scripts/after-import.py"' in package_json
    assert '"check:library": "python scripts/check-library-health.py"' in package_json
    assert '"sync:demo-counts": "python scripts/sync-demo-counts.py --write"' in package_json


def test_sync_demo_counts_updates_the_hard_count_assertions(tmp_path):
    sync = load_script("sync-demo-counts.py")
    demo = tmp_path / "demo-data"
    media = demo / "media"
    media.mkdir(parents=True)
    (media / "img_one.webp").write_bytes(b"webp")
    write_json(
        demo / "items.json",
        [{"first_image": {"original_path": "demo-data/media/img_one.webp"}, "images": []}],
    )
    write_json(demo / "clusters.json", [{"preview_images": ["demo-data/media/img_one.webp"]}, {"preview_images": []}])
    write_json(demo / "tags.json", [{}, {}, {}])
    write_json(demo / "metadata.json", {"item_count": 1})
    test_file = tmp_path / "test_demo.py"
    test_file.write_text(
        "\n".join(
            [
                "assert len(items) == 0",
                "assert len(clusters) == 0",
                "assert len(tags) == 0",
                "assert len(media_files) == 0",
                'assert metadata["item_count"] == 0',
                "assert len(referenced) == 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    counts = sync.demo_counts(demo)
    updated = sync.updated_test_text(test_file, counts)

    assert "assert len(items) == 1" in updated
    assert "assert len(clusters) == 2" in updated
    assert "assert len(tags) == 3" in updated
    assert "assert len(media_files) == 1" in updated
    assert 'assert metadata["item_count"] == 1' in updated
    assert "assert len(referenced) == 1" in updated


def test_library_health_accepts_localized_images_and_demo_counts(tmp_path):
    health = load_script("check-library-health.py")
    library = tmp_path / "library"
    (library / "originals").mkdir(parents=True)
    (library / "originals" / "one.jpg").write_bytes(b"image")
    conn = sqlite3.connect(library / "db.sqlite")
    conn.executescript(
        """
        CREATE TABLE items(id TEXT, title TEXT, source_url TEXT, archived INTEGER, updated_at TEXT);
        CREATE TABLE images(
          id TEXT,
          item_id TEXT,
          original_path TEXT,
          thumb_path TEXT,
          preview_path TEXT,
          remote_url TEXT,
          created_at TEXT
        );
        INSERT INTO items VALUES('itm_one', 'One', 'https://x.com/example/status/1', 0, '2026-05-31');
        INSERT INTO images VALUES('img_one', 'itm_one', 'originals/one.jpg', NULL, NULL, NULL, '2026-05-31');
        """
    )
    conn.commit()
    conn.close()

    demo = tmp_path / "demo-data"
    (demo / "media").mkdir(parents=True)
    (demo / "media" / "img_one.webp").write_bytes(b"webp")
    write_json(
        demo / "items.json",
        [
            {
                "id": "itm_one",
                "slug": "one",
                "first_image": {"original_path": "demo-data/media/img_one.webp"},
                "images": [{"id": "img_one", "original_path": "demo-data/media/img_one.webp"}],
            }
        ],
    )
    write_json(demo / "clusters.json", [{"id": "clu_one", "preview_images": ["demo-data/media/img_one.webp"]}])
    write_json(demo / "tags.json", [])
    write_json(demo / "metadata.json", {"item_count": 1})

    report = health.check_library(library, demo)

    assert report.ok
    assert report.active_count == 1
    assert report.demo_item_count == 1
    assert report.remote_only_images == 0
    assert report.missing_image_active == 0

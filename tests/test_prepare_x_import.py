from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_prepare():
    path = ROOT / "scripts" / "prepare-x-import.py"
    spec = importlib.util.spec_from_file_location("prepare_x_import", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_prepare_x_import_builds_manifest_and_imports_item(tmp_path):
    prepare = load_prepare()
    thread = tmp_path / "thread.json"
    images = tmp_path / "images.json"
    manifest_dir = tmp_path / "manifests"
    library = tmp_path / "library"
    write_json(
        thread,
        {
            "url": "https://nitter.poast.org/example/status/301",
            "tweets": [
                {"href": "/example/status/301#m", "content": "main text"},
                {"href": "/example/status/302#m", "content": "测试提示词\n请生成一张图。"},
            ],
        },
    )
    png = tmp_path / "one.png"
    from PIL import Image

    Image.new("RGB", (12, 12), (20, 40, 80)).save(png)
    write_json(images, {"images": [{"path": str(png)}]})

    result = prepare.prepare_import(
        thread_json=thread,
        images_json=images,
        output_dir=manifest_dir,
        title="Prepared Prompt",
        cluster_name="Prepared Cluster",
        library=str(library),
    )
    duplicate = prepare.prepare_import(
        thread_json=thread,
        images_json=images,
        output_dir=manifest_dir,
        title="Prepared Prompt",
        cluster_name="Prepared Cluster",
        library=str(library),
    )

    assert result["status"] == "created"
    assert result["image_count"] == 1
    assert result["source_url"] == "https://x.com/example/status/301"
    assert Path(result["manifest"]).exists()
    assert duplicate["status"] == "exists"
    conn = sqlite3.connect(library / "db.sqlite")
    conn.row_factory = sqlite3.Row
    item = conn.execute("SELECT title,source_url FROM items").fetchone()
    image = conn.execute("SELECT original_path,remote_url FROM images").fetchone()
    assert dict(item) == {"title": "Prepared Prompt", "source_url": "https://x.com/example/status/301"}
    assert image["remote_url"] is None
    assert (library / image["original_path"]).exists()

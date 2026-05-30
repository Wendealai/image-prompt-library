from __future__ import annotations

import base64
import importlib.util
import json
import sqlite3
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def load_importer():
    path = ROOT / "scripts" / "import-x-prompt.py"
    spec = importlib.util.spec_from_file_location("import_x_prompt", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def png_data_url() -> str:
    buffer = BytesIO()
    Image.new("RGB", (24, 18), (120, 30, 80)).save(buffer, format="PNG")
    payload = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{payload}"


def write_manifest(path: Path, **overrides):
    data = {
        "source_url": "https://x.com/example/status/123",
        "title": "Example X Prompt",
        "author": "@example",
        "prompt_text": "生成一张示例图片。",
        "cluster_name": "Example Cluster",
        "tags": ["X source", "x-status-123"],
        "images": [{"data_url": png_data_url(), "filename": "example.png"}],
    }
    data.update(overrides)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_import_x_prompt_manifest_creates_localized_item(tmp_path):
    importer = load_importer()
    library = tmp_path / "library"
    manifest = tmp_path / "manifest.json"
    write_manifest(manifest)

    result = importer.import_manifest(manifest, library)

    assert result["status"] == "created"
    assert result["image_count"] == 1
    conn = sqlite3.connect(library / "db.sqlite")
    conn.row_factory = sqlite3.Row
    item = conn.execute("SELECT title,source_url,author FROM items").fetchone()
    image = conn.execute("SELECT original_path,thumb_path,preview_path,remote_url,width,height FROM images").fetchone()
    prompts = conn.execute("SELECT language,text FROM prompts ORDER BY is_primary DESC").fetchall()
    tags = [row[0] for row in conn.execute("SELECT name FROM tags ORDER BY name").fetchall()]
    assert dict(item) == {
        "title": "Example X Prompt",
        "source_url": "https://x.com/example/status/123",
        "author": "@example",
    }
    assert image["remote_url"] is None
    assert (library / image["original_path"]).exists()
    assert (library / image["thumb_path"]).exists()
    assert (library / image["preview_path"]).exists()
    assert image["width"] == 24
    assert image["height"] == 18
    assert any(row["language"] == "zh_hans" and "示例图片" in row["text"] for row in prompts)
    assert "x-status-123" in tags


def test_import_x_prompt_manifest_skips_duplicate_source_url(tmp_path):
    importer = load_importer()
    library = tmp_path / "library"
    manifest = tmp_path / "manifest.json"
    write_manifest(manifest)

    first = importer.import_manifest(manifest, library)
    second = importer.import_manifest(manifest, library)

    assert first["status"] == "created"
    assert second["status"] == "exists"
    assert second["item_id"] == first["item_id"]
    conn = sqlite3.connect(library / "db.sqlite")
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM images").fetchone()[0] == 1

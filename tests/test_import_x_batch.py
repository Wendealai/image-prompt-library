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


def load_batch():
    path = ROOT / "scripts" / "import-x-batch.py"
    spec = importlib.util.spec_from_file_location("import_x_batch", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def png_data_url(color: tuple[int, int, int]) -> str:
    buffer = BytesIO()
    Image.new("RGB", (16, 16), color).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def write_manifest(path: Path, status_id: str, color: tuple[int, int, int]) -> None:
    path.write_text(
        json.dumps(
            {
                "source_url": f"https://x.com/example/status/{status_id}",
                "title": f"Prompt {status_id}",
                "author": "@example",
                "prompt_text": "生成一张批量导入测试图。",
                "tags": ["X source", f"x-status-{status_id}"],
                "images": [{"data_url": png_data_url(color), "filename": f"{status_id}.png"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_import_x_batch_imports_directory_and_skips_duplicates(tmp_path):
    batch = load_batch()
    library = tmp_path / "library"
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    write_manifest(manifest_dir / "001.json", "101", (255, 0, 0))
    write_manifest(manifest_dir / "002.json", "102", (0, 255, 0))

    paths = batch._manifest_paths([manifest_dir])
    first = batch.import_batch(paths, library)
    second = batch.import_batch(paths, library)

    assert first["total"] == 2
    assert first["created"] == 2
    assert first["existing"] == 0
    assert second["total"] == 2
    assert second["created"] == 0
    assert second["existing"] == 2
    conn = sqlite3.connect(library / "db.sqlite")
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM images").fetchone()[0] == 2


def test_import_x_batch_deduplicates_input_paths(tmp_path):
    batch = load_batch()
    manifest = tmp_path / "one.json"
    write_manifest(manifest, "201", (0, 0, 255))

    paths = batch._manifest_paths([manifest, manifest])

    assert paths == [manifest.resolve()]

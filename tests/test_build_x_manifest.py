from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_builder():
    path = ROOT / "scripts" / "build-x-manifest.py"
    spec = importlib.util.spec_from_file_location("build_x_manifest", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_build_x_manifest_infers_prompt_reply_and_images(tmp_path):
    builder = load_builder()
    thread = tmp_path / "thread.json"
    images = tmp_path / "images.json"
    output = tmp_path / "manifest.json"
    write_json(
        thread,
        {
            "title": 'Larus Canus (@MrLarus): "main" | nitter.poast.org',
            "url": "https://nitter.poast.org/MrLarus/status/2060000000000000001",
            "tweets": [
                {
                    "href": "/MrLarus/status/2060000000000000001#m",
                    "content": "主帖正文\n提示词见评论区",
                },
                {
                    "href": "/MrLarus/status/2060000000000000002#m",
                    "content": "《测试提示词》\n\n请生成一张高质量商业海报。\n\n设计要求：纯白背景。",
                },
            ],
        },
    )
    write_json(
        images,
        {
            "images": [
                {
                    "dataUrl": "data:image/png;base64," + base64.b64encode(b"image").decode("ascii"),
                    "contentType": "image/png",
                }
            ]
        },
    )

    manifest = builder.build_manifest(
        thread_json=thread,
        images_json=images,
        output=output,
        cluster_name="Posters & Typography",
        tags=["commercial poster"],
    )

    assert output.exists()
    assert manifest["source_url"] == "https://x.com/MrLarus/status/2060000000000000001"
    assert manifest["author"] == "@MrLarus"
    assert manifest["prompt_reply_url"] == "https://x.com/MrLarus/status/2060000000000000002"
    assert manifest["tweet_intro"] == "主帖正文\n提示词见评论区"
    assert "请生成一张高质量商业海报" in manifest["prompt_text"]
    assert manifest["cluster_name"] == "Posters & Typography"
    assert "x-status-2060000000000000001" in manifest["tags"]
    assert "commercial poster" in manifest["tags"]
    assert manifest["images"][0]["data_url"].startswith("data:image/png;base64,")
    assert manifest["images"][0]["content_type"] == "image/png"


def test_build_x_manifest_accepts_explicit_prompt_reply_url(tmp_path):
    builder = load_builder()
    thread = tmp_path / "thread.json"
    images = tmp_path / "images.json"
    output = tmp_path / "manifest.json"
    write_json(
        thread,
        {
            "url": "https://nitter.poast.org/example/status/10",
            "tweets": [
                {"href": "/example/status/10#m", "content": "main"},
                {"href": "/example/status/11#m", "content": "wrong short prompt"},
                {"href": "/example/status/12#m", "content": "right prompt\n请生成一张图。"},
            ],
        },
    )
    write_json(images, {"images": [{"path": "one.jpg"}]})

    manifest = builder.build_manifest(
        thread_json=thread,
        images_json=images,
        output=output,
        prompt_reply_url="https://x.com/example/status/12",
    )

    assert manifest["prompt_reply_url"] == "https://x.com/example/status/12"
    assert manifest["prompt_text"] == "right prompt\n请生成一张图。"
    assert manifest["images"][0]["path"] == "one.jpg"
    assert manifest["images"][0]["filename"] == "one.jpg"

#!/usr/bin/env python3
"""Build and import one X prompt from captured thread/images JSON."""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "tmp" / "x-import-manifests"


def _load_script(filename: str, module_name: str):
    path = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if not spec or not spec.loader:
        raise SystemExit(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manifest_name(thread_json: Path, source_url: str | None) -> str:
    if source_url:
        status = source_url.rstrip("/").rsplit("/", 1)[-1]
        if status.isdigit():
            return f"x-{status}.json"
    stem = thread_json.stem.replace("_thread", "").replace("-thread", "")
    return f"{stem or 'x-prompt'}.manifest.json"


def prepare_import(
    *,
    thread_json: Path,
    images_json: Path,
    output: Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    source_url: str | None = None,
    title: str | None = None,
    author: str | None = None,
    prompt_reply_url: str | None = None,
    cluster_name: str | None = None,
    tags: list[str] | None = None,
    model: str = "ChatGPT Image2",
    prompt_language: str = "zh_hans",
    library: str | None = None,
) -> dict[str, Any]:
    builder = _load_script("build-x-manifest.py", "build_x_manifest_for_prepare")
    importer = _load_script("import-x-prompt.py", "import_x_prompt_for_prepare")
    manifest_path = output or output_dir / _manifest_name(thread_json, source_url)
    manifest = builder.build_manifest(
        thread_json=thread_json,
        images_json=images_json,
        output=manifest_path,
        source_url=source_url,
        title=title,
        author=author,
        prompt_reply_url=prompt_reply_url,
        cluster_name=cluster_name,
        tags=tags or [],
        model=model,
        prompt_language=prompt_language,
    )
    result = importer.import_manifest(manifest_path.resolve(), importer._library_path(library))
    result["manifest"] = str(manifest_path.resolve())
    result["source_url"] = manifest["source_url"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thread-json", type=Path, required=True)
    parser.add_argument("--images-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Manifest path. Defaults to tmp/x-import-manifests/<status>.json")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-url")
    parser.add_argument("--title")
    parser.add_argument("--author")
    parser.add_argument("--prompt-reply-url")
    parser.add_argument("--cluster-name")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--model", default="ChatGPT Image2")
    parser.add_argument("--prompt-language", default="zh_hans")
    parser.add_argument("--library")
    parser.add_argument("--after-import", action="store_true", help="Run scripts/after-import.py after creating a new item")
    args = parser.parse_args()

    result = prepare_import(
        thread_json=args.thread_json.resolve(),
        images_json=args.images_json.resolve(),
        output=args.output.resolve() if args.output else None,
        output_dir=args.output_dir.resolve(),
        source_url=args.source_url,
        title=args.title,
        author=args.author,
        prompt_reply_url=args.prompt_reply_url,
        cluster_name=args.cluster_name,
        tags=args.tag,
        model=args.model,
        prompt_language=args.prompt_language,
        library=args.library,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.after_import and result["status"] == "created":
        subprocess.run([sys.executable, "scripts/after-import.py"], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

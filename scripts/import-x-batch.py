#!/usr/bin/env python3
"""Import one or more X prompt manifests and run post-import maintenance once."""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load_importer():
    path = ROOT / "scripts" / "import-x-prompt.py"
    spec = importlib.util.spec_from_file_location("import_x_prompt", path)
    if not spec or not spec.loader:
        raise SystemExit(f"Could not load importer: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manifest_paths(inputs: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for input_path in inputs:
        resolved = input_path.resolve()
        if resolved.is_dir():
            paths.extend(sorted(resolved.glob("*.json")))
        elif resolved.exists():
            paths.append(resolved)
        else:
            raise SystemExit(f"Manifest path not found: {input_path}")
    seen = set()
    unique = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def import_batch(manifests: list[Path], library_path: Path) -> dict[str, Any]:
    importer = _load_importer()
    results = []
    for manifest in manifests:
        result = importer.import_manifest(manifest, library_path)
        result["manifest"] = str(manifest)
        results.append(result)
    created = [result for result in results if result["status"] == "created"]
    existing = [result for result in results if result["status"] == "exists"]
    return {
        "total": len(results),
        "created": len(created),
        "existing": len(existing),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path, help="Manifest files or directories containing *.json manifests")
    parser.add_argument("--library", help="Library path. Defaults to IMAGE_PROMPT_LIBRARY_PATH or ./library")
    parser.add_argument("--after-import", action="store_true", help="Run scripts/after-import.py once if any new item was created")
    args = parser.parse_args()

    importer = _load_importer()
    paths = _manifest_paths(args.manifests)
    if not paths:
        raise SystemExit("No manifest files found.")
    library_path = importer._library_path(args.library)
    summary = import_batch(paths, library_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.after_import and summary["created"] > 0:
        subprocess.run([sys.executable, "scripts/after-import.py"], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

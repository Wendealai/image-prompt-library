#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import resolve_library_path
from backend.services.prompt_workflow_failures import prompt_workflow_failure_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect stored prompt workflow failure samples.")
    parser.add_argument("--library", help="Override IMAGE_PROMPT_LIBRARY_PATH")
    parser.add_argument("--id", dest="failure_id", help="Show one failure by id")
    parser.add_argument("--limit", type=int, default=10, help="List at most N latest failures")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    library = resolve_library_path(args.library)
    directory = prompt_workflow_failure_dir(library)

    if args.failure_id:
        candidate = directory / f"{args.failure_id}.json"
        if not candidate.is_file():
            print(f"Failure sample not found: {args.failure_id}", file=sys.stderr)
            return 1
        print(candidate.read_text(encoding="utf-8").rstrip())
        return 0

    files = sorted(directory.glob("pwf_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    rows = []
    for path in files[: max(1, args.limit)]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows.append({
            "id": payload.get("id"),
            "created_at": payload.get("created_at"),
            "operation": payload.get("operation"),
            "error_class": payload.get("error_class"),
            "error_message": payload.get("error_message"),
            "path": str(path),
        })
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

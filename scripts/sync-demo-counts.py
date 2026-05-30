#!/usr/bin/env python3
"""Synchronize demo bundle count assertions with the exported demo data."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO_ROOT = ROOT / "frontend" / "public" / "demo-data"
DEFAULT_TEST_FILE = ROOT / "tests" / "test_github_pages_demo.py"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_refs(value: Any, refs: set[str]) -> None:
    if isinstance(value, str) and value.startswith("demo-data/media/"):
        refs.add(value.rsplit("/", 1)[-1])
    elif isinstance(value, dict):
        for child in value.values():
            _collect_refs(child, refs)
    elif isinstance(value, list):
        for child in value:
            _collect_refs(child, refs)


def demo_counts(demo_root: Path = DEFAULT_DEMO_ROOT) -> dict[str, int]:
    items = _load_json(demo_root / "items.json")
    clusters = _load_json(demo_root / "clusters.json")
    tags = _load_json(demo_root / "tags.json")
    metadata = _load_json(demo_root / "metadata.json")
    media_files = list((demo_root / "media").glob("*.webp"))
    refs: set[str] = set()
    _collect_refs(items, refs)
    _collect_refs(clusters, refs)
    return {
        "items": len(items),
        "clusters": len(clusters),
        "tags": len(tags),
        "media_files": len(media_files),
        "referenced": len(refs),
        "metadata_item_count": int(metadata.get("item_count", -1)),
    }


def _replace_count(text: str, pattern: str, replacement: str) -> str:
    next_text, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise SystemExit(f"Could not update assertion matching: {pattern}")
    return next_text


def updated_test_text(test_file: Path, counts: dict[str, int]) -> str:
    text = test_file.read_text(encoding="utf-8")
    text = _replace_count(text, r"assert len\(items\) == \d+", f"assert len(items) == {counts['items']}")
    text = _replace_count(text, r"assert len\(clusters\) == \d+", f"assert len(clusters) == {counts['clusters']}")
    text = _replace_count(text, r"assert len\(tags\) == \d+", f"assert len(tags) == {counts['tags']}")
    text = _replace_count(
        text,
        r"assert len\(media_files\) == \d+",
        f"assert len(media_files) == {counts['media_files']}",
    )
    text = _replace_count(
        text,
        r"assert metadata\[\"item_count\"\] == \d+",
        f"assert metadata[\"item_count\"] == {counts['metadata_item_count']}",
    )
    text = _replace_count(text, r"assert len\(referenced\) == \d+", f"assert len(referenced) == {counts['referenced']}")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-root", type=Path, default=DEFAULT_DEMO_ROOT)
    parser.add_argument("--test-file", type=Path, default=DEFAULT_TEST_FILE)
    parser.add_argument("--write", action="store_true", help="Rewrite the test assertions in place")
    parser.add_argument("--check", action="store_true", help="Fail if the test assertions are stale")
    parser.add_argument("--json", action="store_true", help="Print counts as JSON")
    args = parser.parse_args()

    counts = demo_counts(args.demo_root)
    if counts["items"] != counts["metadata_item_count"]:
        raise SystemExit(f"metadata item_count mismatch: {counts['metadata_item_count']} != {counts['items']}")

    current = args.test_file.read_text(encoding="utf-8")
    updated = updated_test_text(args.test_file, counts)
    if args.json:
        print(json.dumps(counts, ensure_ascii=False, indent=2))
    else:
        print(
            "Demo counts: "
            f"items={counts['items']}, clusters={counts['clusters']}, tags={counts['tags']}, "
            f"media={counts['media_files']}, referenced={counts['referenced']}"
        )

    if args.write:
        if updated != current:
            args.test_file.write_text(updated, encoding="utf-8")
            print(f"Updated {args.test_file}")
        return 0

    if args.check and updated != current:
        print(f"{args.test_file} has stale demo count assertions. Run python scripts/sync-demo-counts.py --write.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

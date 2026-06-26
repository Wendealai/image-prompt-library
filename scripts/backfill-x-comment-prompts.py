#!/usr/bin/env python3
"""Backfill missing X/Twitter prompt text from comment threads for existing items."""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.repositories import ItemRepository
from backend.schemas import ItemUpdate, PromptIn

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _load_module(script_name: str, module_name: str):
    path = ROOT / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(module_name, path)
    if not spec or not spec.loader:
        raise SystemExit(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


IMPORTER = _load_module("import-x-prompt.py", "import_x_prompt_backfill")
GALLERY = _load_module("import-x-gallery-dl-batch.py", "import_x_gallery_dl_batch_backfill")


def _tweet_intro_from_notes(notes: str | None) -> str:
    if not notes:
        return ""
    match = re.search(r"Original tweet intro:\n(.+)", notes, re.S)
    return match.group(1).strip() if match else ""


def _structured_candidate(notes: str | None, prompt_text: str) -> bool:
    intro = _tweet_intro_from_notes(notes)
    markers = (
        "评论区",
        "见评论",
        "在评论",
        "评论见",
        "下方评论",
        "评论区见",
        "见评论区",
        "提示词放评论区",
        "提示词见评论区",
        "in comments",
        "comment section",
        "comments below",
        "prompt below",
        "prompt in comments",
        "see comments",
        "check comments",
    )
    haystack = f"{notes or ''}\n{intro}".lower()
    prompt = prompt_text.strip()
    return (
        any(marker.lower() in haystack for marker in markers)
        or prompt == intro.strip()
        or len(prompt) < 220
        or (intro and len(prompt) * 2 < len(intro))
    )


def _prompt_quality_score(text: str, intro: str) -> int:
    clean = text.strip()
    if not clean:
        return -1000
    score = len(clean)
    if clean == intro.strip():
        score -= 400
    if GALLERY._looks_like_prompt_text(clean):
        score += 400
    if GALLERY._points_to_replies(clean):
        score -= 250
    if clean.lower().startswith(("prompt below", "prompt in comments")):
        score -= 250
    return score


def _should_update_prompt(current_prompt: str, new_prompt: str, intro: str, reply_url: str | None) -> bool:
    current = current_prompt.strip()
    new = new_prompt.strip()
    if not new or new == current:
        return False
    if len(current) >= 220 and len(new) < int(len(current) * 0.8):
        return False
    current_score = _prompt_quality_score(current, intro)
    new_score = _prompt_quality_score(new, intro)
    if current == intro.strip() and new != current:
        return True
    if reply_url and len(current) < 220 and len(new) >= len(current) + 20 and new_score >= current_score:
        return True
    if len(current) < 220 and len(new) >= len(current) + 60 and new_score >= current_score + 80:
        return True
    if new_score >= current_score + 120:
        return True
    if len(new) >= len(current) + 120 and len(new) >= 160:
        return True
    if len(new) > int(len(current) * 1.35) and len(new) >= 140:
        return True
    return False


def _candidate_rows(
    library_path: Path,
    *,
    item_ids: set[str] | None = None,
    source_urls: set[str] | None = None,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    with sqlite3.connect(library_path / "db.sqlite") as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT i.id, i.title, i.source_url, i.author, i.notes, p.language, p.text
            FROM items i
            JOIN prompts p ON p.item_id = i.id AND p.is_primary = 1
            WHERE i.archived = 0
              AND i.source_name = 'X / Twitter'
            ORDER BY i.created_at DESC
            """
        ).fetchall()
    filtered: list[sqlite3.Row] = []
    for row in rows:
        if item_ids and row["id"] not in item_ids:
            continue
        if source_urls and row["source_url"] not in source_urls:
            continue
        if not item_ids and not source_urls and not _structured_candidate(row["notes"], row["text"]):
            continue
        filtered.append(row)
        if limit is not None and len(filtered) >= limit:
            break
    return filtered


def run_backfill(
    *,
    library_path: Path,
    item_ids: set[str] | None = None,
    source_urls: set[str] | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    repo = ItemRepository(library_path)
    candidates = _candidate_rows(library_path, item_ids=item_ids, source_urls=source_urls, limit=limit)
    results: list[dict[str, Any]] = []
    updated = 0
    skipped = 0
    failed = 0
    for row in candidates:
        intro = _tweet_intro_from_notes(row["notes"])
        try:
            _, manifest = GALLERY._manifest_for(
                row["source_url"],
                ROOT / "tmp" / "x-backfill-dry-run",
                dry_run=True,
            )
            new_prompt = manifest["prompt_text"]
            reply_url = manifest.get("prompt_reply_url")
            should_update = _should_update_prompt(row["text"], new_prompt, intro, reply_url)
            result = {
                "item_id": row["id"],
                "title": row["title"],
                "source_url": row["source_url"],
                "status": "skipped",
                "current_length": len((row["text"] or "").strip()),
                "new_length": len(new_prompt.strip()),
                "reply_url": reply_url,
            }
            if should_update:
                result["status"] = "would_update" if dry_run else "updated"
                if not dry_run:
                    notes = IMPORTER._notes(
                        {
                            "tweet_intro": manifest.get("tweet_intro"),
                            "prompt_reply_url": reply_url,
                        },
                        row["source_url"],
                        row["author"],
                    )
                    repo.update_item(
                        row["id"],
                        ItemUpdate(
                            notes=notes,
                            prompts=[PromptIn(language=manifest.get("prompt_language") or row["language"] or "zh_hans", text=new_prompt, is_primary=True)],
                        ),
                    )
                    updated += 1
            else:
                skipped += 1
            results.append(result)
        except Exception as exc:
            failed += 1
            results.append(
                {
                    "item_id": row["id"],
                    "title": row["title"],
                    "source_url": row["source_url"],
                    "status": "error",
                    "error": str(exc),
                }
            )
    if updated and not dry_run:
        subprocess.run([sys.executable, "scripts/after-import.py"], cwd=ROOT, check=True)
    return {
        "total_candidates": len(candidates),
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "dry_run": dry_run,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", help="Library path. Defaults to ./library")
    parser.add_argument("--item-id", action="append", default=[])
    parser.add_argument("--source-url", action="append", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    summary = run_backfill(
        library_path=IMPORTER._library_path(args.library),
        item_ids={value.strip() for value in args.item_id if value.strip()} or None,
        source_urls={value.strip() for value in args.source_url if value.strip()} or None,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

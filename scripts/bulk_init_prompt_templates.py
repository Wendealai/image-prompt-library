from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.repositories import ItemRepository
from backend.routers.prompt_templates import (
    _initialize_template_for_item_with_bulk_fallback,
    _initialize_template_for_item_with_local_fallback,
)
from backend.services.prompt_workflows import PromptWorkflowError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(handle: TextIO | None, payload: dict) -> None:
    line = json.dumps({"ts": _now(), **payload}, ensure_ascii=False)
    print(line, flush=True)
    if handle:
        handle.write(line + "\n")
        handle.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize prompt skeleton templates through the configured n8n workflow.")
    parser.add_argument("--library", default="library", help="Library directory containing db.sqlite.")
    parser.add_argument("--mode", choices=["missing", "stale", "all"], default="missing", help="Which inventory slice to process.")
    parser.add_argument("--language", default=None, help="Optional prompt language override, for example zh_hans or en.")
    parser.add_argument("--limit", type=int, default=500, help="Maximum number of items to process.")
    parser.add_argument("--fallback-only", action="store_true", help="Skip n8n and create deterministic local fallback templates.")
    parser.add_argument("--log", type=Path, default=None, help="Optional JSONL progress log path.")
    parser.add_argument("--result", type=Path, default=None, help="Optional summary JSON path.")
    args = parser.parse_args()

    repo = ItemRepository(Path(args.library))
    total_candidates = repo.count_prompt_template_init_candidates(args.mode)
    candidates = repo.list_prompt_template_init_candidates(args.mode, max(1, min(args.limit, 500)))
    processed = 0
    failed = 0
    failures: list[dict[str, str]] = []

    log_handle = None
    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        log_handle = args.log.open("a", encoding="utf-8")

    try:
        _emit(log_handle, {
            "event": "batch_start",
            "mode": args.mode,
            "language": args.language,
            "total_candidates": total_candidates,
            "selected_count": len(candidates),
        })
        for index, candidate in enumerate(candidates, start=1):
            item_id = str(candidate["item_id"])
            title = str(candidate["title"])
            _emit(log_handle, {
                "event": "item_start",
                "index": index,
                "selected_count": len(candidates),
                "item_id": item_id,
                "title": title,
            })
            try:
                if args.fallback_only:
                    template = _initialize_template_for_item_with_local_fallback(
                        repo,
                        item_id,
                        args.language,
                        PromptWorkflowError("n8n init skipped for fallback-only bulk recovery."),
                    )
                else:
                    template = _initialize_template_for_item_with_bulk_fallback(repo, item_id, args.language)
                processed += 1
                _emit(log_handle, {
                    "event": "item_done",
                    "index": index,
                    "item_id": item_id,
                    "title": title,
                    "template_id": template.id,
                    "slot_count": len(template.slots),
                    "processed": processed,
                    "failed": failed,
                })
            except Exception as exc:  # noqa: BLE001
                failed += 1
                failure = {"item_id": item_id, "title": title, "error": str(exc)}
                failures.append(failure)
                _emit(log_handle, {
                    "event": "item_failed",
                    "index": index,
                    **failure,
                    "traceback": traceback.format_exc(limit=2),
                    "processed": processed,
                    "failed": failed,
                })

        summary = {
            "mode": args.mode,
            "language": args.language,
            "total_candidates": total_candidates,
            "selected_count": len(candidates),
            "remaining_missing": repo.count_prompt_template_init_candidates("missing"),
            "processed": processed,
            "failed": failed,
            "failures": failures,
        }
        if args.result:
            args.result.parent.mkdir(parents=True, exist_ok=True)
            args.result.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        _emit(log_handle, {"event": "batch_complete", **summary})
    finally:
        if log_handle:
            log_handle.close()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.config import resolve_library_path
from backend.services.canghe_gallery_sync import CANGHE_CASES_URL, sync_canghe_gallery


def _remote_sync(args: argparse.Namespace) -> dict:
    password = args.admin_password or os.environ.get("IMAGE_PROMPT_LIBRARY_ADMIN_PASSWORD") or os.environ.get("CANGHE_SYNC_ADMIN_PASSWORD")
    if not password:
        raise SystemExit("Remote sync requires --admin-password or IMAGE_PROMPT_LIBRARY_ADMIN_PASSWORD.")
    base_url = args.base_url.rstrip("/")
    payload = {
        "admin_password": password,
        "dry_run": args.dry_run,
        "max_imports": args.max_imports,
        "initialize_templates": args.init_templates,
        "approve_templates": args.approve_templates,
    }
    with httpx.Client(follow_redirects=True, timeout=args.timeout) as client:
        response = client.post(f"{base_url}/api/admin/intake/canghe-gallery/sync", json=payload)
        response.raise_for_status()
        return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Incrementally sync gpt-image2.canghe.ai gallery cases into Image Prompt Library.")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--base-url", help="Remote Image Prompt Library base URL, for example https://prompt.wendealai.com")
    target.add_argument("--library", help="Local library path. Defaults to IMAGE_PROMPT_LIBRARY_PATH or ./library when --base-url is omitted.")
    parser.add_argument("--source-url", default=CANGHE_CASES_URL, help="Canghe cases.json URL.")
    parser.add_argument("--admin-password", help="Admin password for remote sync. Prefer env vars for scheduled runs.")
    parser.add_argument("--dry-run", action="store_true", help="Report incremental candidates without importing.")
    parser.add_argument("--max-imports", type=int, default=50, help="Maximum new cases to import or report.")
    parser.add_argument("--init-templates", action="store_true", help="Initialize prompt skeleton templates for imported items.")
    parser.add_argument("--approve-templates", action="store_true", help="Approve initialized prompt templates.")
    parser.add_argument("--timeout", type=float, default=300, help="Remote API timeout in seconds.")
    args = parser.parse_args()

    if args.base_url:
        payload = _remote_sync(args)
    else:
        library = Path(args.library) if args.library else resolve_library_path()
        payload = sync_canghe_gallery(
            library,
            source_url=args.source_url,
            dry_run=args.dry_run,
            max_imports=args.max_imports,
            initialize_templates=args.init_templates,
            approve_templates=args.approve_templates,
        ).model_dump()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPStatusError as exc:
        print(exc.response.text, file=sys.stderr)
        raise

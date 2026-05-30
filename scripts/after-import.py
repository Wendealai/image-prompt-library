#!/usr/bin/env python3
"""Post-import maintenance: export demo data, sync count tests, and run health checks."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str]) -> None:
    print(f"$ {' '.join(args)}", flush=True)
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-export", action="store_true", help="Reuse the existing frontend/public/demo-data bundle")
    parser.add_argument("--skip-count-sync", action="store_true", help="Do not rewrite demo count assertions")
    args = parser.parse_args()

    if not args.skip_export:
        _run([sys.executable, "scripts/export-demo-data.py"])
    if not args.skip_count_sync:
        _run([sys.executable, "scripts/sync-demo-counts.py", "--write"])
    _run([sys.executable, "scripts/check-library-health.py"])
    print("Post-import maintenance complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

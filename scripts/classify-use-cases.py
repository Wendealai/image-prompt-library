from __future__ import annotations

import argparse
from pathlib import Path

from backend.db import init_db
from backend.repositories import ItemRepository
from backend.services.use_case_classifier import use_case_sort_key


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill top-level use-case categories for items.")
    parser.add_argument("--library", default="library", help="Library directory containing db.sqlite")
    parser.add_argument("--limit", type=int, default=None, help="Only process the most recent N items")
    args = parser.parse_args()

    library = Path(args.library).resolve()
    init_db(library)
    repository = ItemRepository(library)
    counts = repository.backfill_use_cases(limit=args.limit)
    total = sum(counts.values())
    print(f"classified_items={total}")
    for name, count in sorted(counts.items(), key=lambda item: (-item[1], use_case_sort_key(item[0]))):
        print(f"{name}\t{count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

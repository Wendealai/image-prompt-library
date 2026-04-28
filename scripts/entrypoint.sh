#!/usr/bin/env sh
set -eu

LIBRARY_PATH="${IMAGE_PROMPT_LIBRARY_PATH:-/data/library}"

if [ "${IMPORT_DEMO_DATA_ON_START:-0}" = "1" ]; then
  item_total="$(
    python - <<'PY'
import os
from pathlib import Path
from backend.repositories import ItemRepository

library = Path(os.environ.get("IMAGE_PROMPT_LIBRARY_PATH", "/data/library"))
print(ItemRepository(library).list_items(limit=1).total)
PY
  )"
  if [ "$item_total" = "0" ]; then
    python /app/scripts/import-demo-data.py --public-v0.1 --library "$LIBRARY_PATH"
  fi
fi

exec python -m uvicorn backend.main:app --host "${BACKEND_HOST:-0.0.0.0}" --port "${BACKEND_PORT:-8000}"

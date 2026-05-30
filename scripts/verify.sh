#!/usr/bin/env bash
set -euo pipefail

python -m ruff check backend tests scripts
python -m pytest -q
if [ -f "./library/db.sqlite" ]; then
  python scripts/check-library-health.py
else
  echo "Skipping library health check: ./library/db.sqlite not found."
fi
npm run lint
npm run build
npm run build:demo

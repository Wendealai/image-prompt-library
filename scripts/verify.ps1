$ErrorActionPreference = "Stop"

python -m ruff check backend tests scripts
python -m pytest -q
npm run lint
npm run build
npm run build:demo

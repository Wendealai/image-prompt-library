$ErrorActionPreference = "Stop"

python -m ruff check backend tests scripts
python -m pytest -q
if (Test-Path ".\library\db.sqlite") {
    python scripts/check-library-health.py
} else {
    Write-Host "Skipping library health check: .\library\db.sqlite not found."
}
npm run lint
npm run build
npm run build:demo

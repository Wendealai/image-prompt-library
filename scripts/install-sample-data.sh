#!/usr/bin/env bash
set -euo pipefail

LANGUAGE="${1:-}"
if [[ -z "$LANGUAGE" ]]; then
  echo "Usage: $0 <en|zh_hans|zh_hant>" >&2
  exit 2
fi
case "$LANGUAGE" in
  en|zh_hans|zh_hant) ;;
  *) echo "Unsupported sample language: $LANGUAGE" >&2; exit 2 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LIBRARY_PATH="${IMAGE_PROMPT_LIBRARY_PATH:-$REPO_ROOT/library}"
MANIFEST_PATH="${SAMPLE_DATA_MANIFEST:-$REPO_ROOT/sample-data/manifests/$LANGUAGE.json}"
WORK_DIR="${SAMPLE_DATA_WORK_DIR:-$REPO_ROOT/.local-work/sample-data-installer}"
ASSET_DIR="${SAMPLE_DATA_IMAGE_DIR:-}"
IMAGE_ZIP="${SAMPLE_DATA_IMAGE_ZIP:-}"
RELEASE_BASE_URL="${SAMPLE_DATA_RELEASE_BASE_URL:-https://github.com/EddieTYP/image-prompt-library/releases/download/sample-data-v1}"
RELEASE_ASSET_NAME="${SAMPLE_DATA_RELEASE_ASSET_NAME:-image-prompt-library-sample-images-v1.zip}"
EXPECTED_SHA256="${SAMPLE_DATA_IMAGE_ZIP_SHA256:-8a458f6c8c96079f40fbc46c689e7de0bd2eb464ee7f800f94f3ca60131d5035}"

sha256_file() {
  local file="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file" | awk '{print $1}'
  else
    echo "Neither sha256sum nor shasum is available for checksum verification" >&2
    return 1
  fi
}

verify_zip_checksum() {
  local file="$1"
  local expected="$2"
  if [[ -z "$expected" ]]; then
    return 0
  fi
  local actual
  actual="$(sha256_file "$file")"
  if [[ "$actual" != "$expected" ]]; then
    echo "Sample image ZIP checksum mismatch: $file" >&2
    echo "Expected: $expected" >&2
    echo "Actual:   $actual" >&2
    exit 1
  fi
}

if [[ ! -f "$MANIFEST_PATH" ]]; then
  echo "Sample manifest not found: $MANIFEST_PATH" >&2
  exit 1
fi

mkdir -p "$WORK_DIR"
if [[ -z "$ASSET_DIR" ]]; then
  ASSET_DIR="$WORK_DIR/images"
  rm -rf "$ASSET_DIR"
  mkdir -p "$ASSET_DIR"
  if [[ -n "$IMAGE_ZIP" ]]; then
    if [[ ! -f "$IMAGE_ZIP" ]]; then
      echo "Sample image ZIP not found: $IMAGE_ZIP" >&2
      exit 1
    fi
    if [[ -n "${SAMPLE_DATA_IMAGE_ZIP_SHA256:-}" ]]; then
      verify_zip_checksum "$IMAGE_ZIP" "$EXPECTED_SHA256"
    fi
    unzip -q "$IMAGE_ZIP" -d "$ASSET_DIR"
  else
    IMAGE_ZIP="$WORK_DIR/$RELEASE_ASSET_NAME"
    echo "Downloading sample images from $RELEASE_BASE_URL/$RELEASE_ASSET_NAME"
    curl -fL "$RELEASE_BASE_URL/$RELEASE_ASSET_NAME" -o "$IMAGE_ZIP"
    verify_zip_checksum "$IMAGE_ZIP" "$EXPECTED_SHA256"
    unzip -q "$IMAGE_ZIP" -d "$ASSET_DIR"
  fi
fi

PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON:-python3}"
fi

RESULT_JSON="$($PYTHON_BIN -m backend.services.import_sample_bundle \
  --manifest "$MANIFEST_PATH" \
  --assets "$ASSET_DIR" \
  --library "$LIBRARY_PATH")"

ITEMS="$($PYTHON_BIN -c 'import json,sys; print(json.load(sys.stdin)["item_count"])' <<<"$RESULT_JSON")"
IMAGES="$($PYTHON_BIN -c 'import json,sys; print(json.load(sys.stdin)["image_count"])' <<<"$RESULT_JSON")"
LOG="$($PYTHON_BIN -c 'import json,sys; print(json.load(sys.stdin).get("log", ""))' <<<"$RESULT_JSON")"

echo "Imported $ITEMS items and $IMAGES images into $LIBRARY_PATH"
if [[ -n "$LOG" ]]; then
  echo "$LOG"
fi

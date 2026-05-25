#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
N8N_DIR="$ROOT_DIR/automation/n8n"
N8N_URL_VALUE="${N8N_URL:-${N8N_BASE_URL:-}}"
N8N_API_KEY_VALUE="${N8N_API_KEY:-}"
CLI_HOME="${N8N_CLI_HOME:-/tmp/n8n-cli-home}"
NPM_CACHE_DIR="${N8N_NPM_CACHE_DIR:-/tmp/npm-cache}"

if [[ -z "$N8N_URL_VALUE" || -z "$N8N_API_KEY_VALUE" ]]; then
  echo "N8N_URL (or N8N_BASE_URL) and N8N_API_KEY are required." >&2
  exit 1
fi

mkdir -p "$CLI_HOME" "$NPM_CACHE_DIR"

node "$N8N_DIR/build-workflows.mjs"

n8n_cli() {
  HOME="$CLI_HOME" npm_config_cache="$NPM_CACHE_DIR" npx -y @n8n/cli "$@"
}

upsert_workflow() {
  local name="$1"
  local file="$2"
  local workflow_id
  workflow_id="$({
    n8n_cli workflow list --url="$N8N_URL_VALUE" --apiKey="$N8N_API_KEY_VALUE" --name="$name" --limit=20 --json \
      | jq -r --arg name "$name" 'map(select(.name == $name and (.isArchived | not)))[0].id // empty'
  })"

  if [[ -n "$workflow_id" ]]; then
    echo "Updating workflow: $name ($workflow_id)" >&2
    n8n_cli workflow update "$workflow_id" --url="$N8N_URL_VALUE" --apiKey="$N8N_API_KEY_VALUE" --file="$file" --quiet >/dev/null
  else
    echo "Creating workflow: $name" >&2
    workflow_id="$(n8n_cli workflow create --url="$N8N_URL_VALUE" --apiKey="$N8N_API_KEY_VALUE" --file="$file" --json | jq -r '.id')"
  fi

  n8n_cli workflow activate "$workflow_id" --url="$N8N_URL_VALUE" --apiKey="$N8N_API_KEY_VALUE" --quiet >/dev/null
  printf '%s\n' "$workflow_id"
}

INIT_ID="$(upsert_workflow 'Image Prompt Library - Template Init' "$N8N_DIR/prompt-template-init.workflow.json")"
GENERATE_ID="$(upsert_workflow 'Image Prompt Library - Template Generate' "$N8N_DIR/prompt-template-generate.workflow.json")"
CANGHE_WORKFLOW_FILE="$N8N_DIR/canghe-gallery-daily-sync.workflow.json"
CANGHE_UPLOAD_WORKFLOW="$CANGHE_WORKFLOW_FILE"
CANGHE_TEMP_WORKFLOW=""
if [[ -n "${IMAGE_PROMPT_LIBRARY_ADMIN_PASSWORD:-}" ]]; then
  CANGHE_TEMP_WORKFLOW="$(mktemp)"
  python3 - <<'PY' "$CANGHE_WORKFLOW_FILE" "$CANGHE_TEMP_WORKFLOW" "$IMAGE_PROMPT_LIBRARY_ADMIN_PASSWORD"
import json
import sys

source, target, password = sys.argv[1:4]
workflow = json.load(open(source, "r", encoding="utf-8"))
for node in workflow.get("nodes", []):
    if node.get("name") == "Call Image Prompt Library Canghe Sync":
        parameters = node.setdefault("parameters", {})
        parameters["jsonBody"] = (
            "={{ { admin_password: "
            + json.dumps(password)
            + ", dry_run: false, max_imports: 80, initialize_templates: true, approve_templates: false } }}"
        )
json.dump(workflow, open(target, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
  CANGHE_UPLOAD_WORKFLOW="$CANGHE_TEMP_WORKFLOW"
fi
CANGHE_ID="$(upsert_workflow 'Image Prompt Library - Canghe Gallery Daily Sync' "$CANGHE_UPLOAD_WORKFLOW")"
if [[ -n "$CANGHE_TEMP_WORKFLOW" ]]; then
  rm -f "$CANGHE_TEMP_WORKFLOW"
fi

cat <<OUT
INIT_WORKFLOW_ID=$INIT_ID
GENERATE_WORKFLOW_ID=$GENERATE_ID
CANGHE_GALLERY_SYNC_WORKFLOW_ID=$CANGHE_ID
IMAGE_PROMPT_TEMPLATE_INIT_WEBHOOK_URL=$N8N_URL_VALUE/webhook/image-prompt-library-template-init
IMAGE_PROMPT_TEMPLATE_GENERATE_WEBHOOK_URL=$N8N_URL_VALUE/webhook/image-prompt-library-template-generate
OUT

# Restore source-controlled workflow JSON without embedding live secrets.
env -u IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN -u IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN_HEADER node "$N8N_DIR/build-workflows.mjs"

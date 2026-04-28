# Image Prompt Library n8n Workflows

This directory version-controls the two AI workflows used by the app:

- `Image Prompt Library - Template Init`
- `Image Prompt Library - Template Generate`

They are built from the `*.prepare.js` and `*.format.js` code files by `build-workflows.mjs`.

## Sync to n8n

Set these environment variables first:

- `N8N_URL` or `N8N_BASE_URL`
- `N8N_API_KEY`

Then run:

```bash
./scripts/sync-n8n-prompt-workflows.sh
```

The script will:

1. build the workflow JSON files
2. create or update the workflows in n8n
3. activate them
4. print the webhook URLs you should place in the app environment

## App Environment

The backend expects these variables:

- `IMAGE_PROMPT_TEMPLATE_INIT_WEBHOOK_URL`
- `IMAGE_PROMPT_TEMPLATE_GENERATE_WEBHOOK_URL`
- `IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN` (optional; only if you add workflow-side auth)
- `IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN_HEADER` (optional; defaults to `Authorization`)
- `IMAGE_PROMPT_TEMPLATE_TIMEOUT_SECONDS` (optional; defaults to `45`)

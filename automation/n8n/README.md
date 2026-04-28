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
- `IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN` (optional; set the same value on the app and the n8n service if you enable auth)
- `IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN_HEADER` (optional; defaults to `X-Image-Prompt-Workflow-Token`)
- `IMAGE_PROMPT_TEMPLATE_TIMEOUT_SECONDS` (optional; defaults to `45`)

## Optional Webhook Auth

The generated workflows now include an auth gate node ahead of the AI call. Auth stays disabled until `IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN` is present in the n8n runtime environment.

If you enable it:

1. set `IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN` on the app backend
2. set the same `IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN` on the n8n service
3. optionally set `IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN_HEADER` on both sides if you do not want to use `X-Image-Prompt-Workflow-Token`

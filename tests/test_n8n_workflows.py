from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
N8N_DIR = ROOT / 'automation' / 'n8n'


@pytest.mark.parametrize(
    ('filename', 'webhook_name', 'auth_name', 'prepare_name'),
    [
        (
            'prompt-template-init.workflow.json',
            'Webhook Prompt Template Init',
            'Authorize Prompt Template Init Request',
            'Prepare Prompt Template Init Payload',
        ),
        (
            'prompt-template-generate.workflow.json',
            'Webhook Prompt Template Generate',
            'Authorize Prompt Template Generate Request',
            'Prepare Prompt Template Generate Payload',
        ),
    ],
)
def test_prompt_template_workflows_include_auth_gate(filename: str, webhook_name: str, auth_name: str, prepare_name: str):
    workflow = json.loads((N8N_DIR / filename).read_text(encoding='utf-8'))
    node_names = {node['name'] for node in workflow['nodes']}
    auth_node = next(node for node in workflow['nodes'] if node['name'] == auth_name)
    auth_code = auth_node['parameters']['jsCode']

    assert auth_name in node_names
    assert workflow['connections'][webhook_name]['main'][0][0]['node'] == auth_name
    assert workflow['connections'][auth_name]['main'][0][0]['node'] == prepare_name
    assert 'const expectedToken = "";' in auth_code
    assert 'X-Image-Prompt-Workflow-Token' in auth_code


def test_prompt_template_init_workflow_uses_prompt_markers_and_cleanup_guard():
    workflow = json.loads((N8N_DIR / 'prompt-template-init.workflow.json').read_text(encoding='utf-8'))
    prepare_node = next(node for node in workflow['nodes'] if node['name'] == 'Prepare Prompt Template Init Payload')
    format_node = next(node for node in workflow['nodes'] if node['name'] == 'Format Prompt Template Init Output')

    prepare_code = prepare_node['parameters']['jsCode']
    format_code = format_node['parameters']['jsCode']

    assert '<<<IMAGE_PROMPT_BEGIN>>>' in prepare_code
    assert '<<<IMAGE_PROMPT_END>>>' in prepare_code
    assert 'Only the text between those markers belongs to the original prompt.' in prepare_code
    assert 'Do not include the boundary markers or any follow-up instructions in markedText.' in prepare_code
    assert 'Never nest one slot inside another slot.' in prepare_code
    assert 'Never create overlapping slots.' in prepare_code
    assert 'temperature: 0' in prepare_code
    assert 'removePromptScaffolding' in format_code
    assert "const trailingInstructions = [" in format_code
    assert "cleaned = cleaned.replace(new RegExp(`\\\\n+${escaped}\\\\s*$`, 'i'), '').trimEnd();" in format_code


def test_canghe_gallery_daily_sync_workflow_calls_admin_sync_endpoint_without_embedded_password():
    workflow = json.loads((N8N_DIR / 'canghe-gallery-daily-sync.workflow.json').read_text(encoding='utf-8'))
    node_names = {node['name'] for node in workflow['nodes']}
    request_node = next(node for node in workflow['nodes'] if node['name'] == 'Call Image Prompt Library Canghe Sync')
    body = request_node['parameters']['jsonBody']

    assert 'Schedule Canghe Gallery Daily Sync' in node_names
    assert 'Summarize Canghe Gallery Sync Result' in node_names
    assert request_node['parameters']['url'] == 'https://prompt.wendealai.com/api/admin/intake/canghe-gallery/sync'
    assert '$env.IMAGE_PROMPT_LIBRARY_ADMIN_PASSWORD' in body
    assert 'zwyy0323' not in body
    assert workflow['connections']['Schedule Canghe Gallery Daily Sync']['main'][0][0]['node'] == 'Call Image Prompt Library Canghe Sync'


def test_n8n_sync_script_injects_canghe_password_only_for_upload():
    script = (ROOT / 'scripts' / 'sync-n8n-prompt-workflows.sh').read_text(encoding='utf-8')

    assert 'IMAGE_PROMPT_LIBRARY_ADMIN_PASSWORD' in script
    assert 'CANGHE_TEMP_WORKFLOW="$(mktemp)"' in script
    assert 'CANGHE_UPLOAD_WORKFLOW="$CANGHE_TEMP_WORKFLOW"' in script
    assert "json.dumps(password)" in script

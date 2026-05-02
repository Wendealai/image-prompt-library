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

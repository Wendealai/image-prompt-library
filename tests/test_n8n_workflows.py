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


@pytest.mark.parametrize(
    ('filename', 'prepare_name', 'required_snippets'),
    [
        (
            'prompt-template-init.workflow.json',
            'Prepare Prompt Template Init Payload',
            [
                'defaultImportSkillUrl',
                'Default import skill URL:',
                'Apply the synced default import skill URL above as background import guidance.',
                'Source URL:',
                'Author:',
                'Item notes:',
            ],
        ),
        (
            'prompt-template-generate.workflow.json',
            'Prepare Prompt Template Generate Payload',
            [
                'defaultImportSkillUrl',
                'Default import skill URL:',
                'Apply the synced default import skill URL above as background rewrite guidance.',
                'Source URL:',
                'Author:',
                'Item notes:',
            ],
        ),
    ],
)
def test_prompt_template_workflows_include_default_import_skill_context(
    filename: str,
    prepare_name: str,
    required_snippets: list[str],
):
    workflow = json.loads((N8N_DIR / filename).read_text(encoding='utf-8'))
    prepare_node = next(node for node in workflow['nodes'] if node['name'] == prepare_name)
    prepare_code = prepare_node['parameters']['jsCode']

    for snippet in required_snippets:
        assert snippet in prepare_code

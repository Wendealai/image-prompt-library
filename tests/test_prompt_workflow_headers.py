from __future__ import annotations

from backend.services.prompt_workflows import _workflow_headers


def test_workflow_headers_use_custom_header_by_default(monkeypatch):
    monkeypatch.setenv('IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN', 'secret-token')
    monkeypatch.delenv('IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN_HEADER', raising=False)

    assert _workflow_headers() == {
        'X-Image-Prompt-Workflow-Token': 'secret-token',
    }


def test_workflow_headers_support_authorization_when_explicitly_requested(monkeypatch):
    monkeypatch.setenv('IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN', 'secret-token')
    monkeypatch.setenv('IMAGE_PROMPT_TEMPLATE_WORKFLOW_TOKEN_HEADER', 'Authorization')

    assert _workflow_headers() == {
        'Authorization': 'Bearer secret-token',
    }

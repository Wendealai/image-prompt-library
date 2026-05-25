from __future__ import annotations

import pytest

from backend.services.prompt_workflows import PromptWorkflowError, initialize_prompt_template


RAW_PROMPT = 'A cinematic poster of a tiny ramen bar with paper lanterns and wooden stools.'
MARKED_PROMPT = 'A cinematic poster of [[slot id="main_subject" group="theme_core" label="主体"]]a tiny ramen bar[[/slot]] with [[slot id="support_props" group="theme_core" label="配套元素"]]paper lanterns and wooden stools[[/slot]].'


def test_initialize_prompt_template_retries_once_on_retryable_workflow_error(monkeypatch):
    monkeypatch.setenv('IMAGE_PROMPT_TEMPLATE_INIT_WEBHOOK_URL', 'https://n8n.example/webhook/image-prompt-library-template-init')

    calls = {'count': 0}

    def fake_post_json(url: str, payload: dict, *, operation: str):
        calls['count'] += 1
        assert url == 'https://n8n.example/webhook/image-prompt-library-template-init'
        assert operation == 'template_init'
        assert payload['prompt']['text'] == RAW_PROMPT
        if calls['count'] == 1:
            raise PromptWorkflowError(
                'Workflow request failed: markedText does not render back to the original prompt exactly.',
                operation='template_init',
                url=url,
                request_payload=payload,
                response_status=502,
                response_text='markedText does not render back to the original prompt exactly.',
            )
        return {
            'markedText': MARKED_PROMPT,
            'confidence': 0.93,
            'notes': 'Recovered on retry.',
            'sourceLanguage': 'en',
        }

    monkeypatch.setattr('backend.services.prompt_workflows._post_json', fake_post_json)

    result = initialize_prompt_template(
        item_id='itm_test',
        title='Midnight Noodles',
        model='Image generation prompt',
        source_language='en',
        raw_text=RAW_PROMPT,
    )

    assert calls['count'] == 2
    assert result == {
        'marked_text': MARKED_PROMPT,
        'analysis_confidence': 0.93,
        'analysis_notes': 'Recovered on retry.',
        'source_language': 'en',
    }


def test_initialize_prompt_template_does_not_retry_non_retryable_workflow_error(monkeypatch):
    monkeypatch.setenv('IMAGE_PROMPT_TEMPLATE_INIT_WEBHOOK_URL', 'https://n8n.example/webhook/image-prompt-library-template-init')

    calls = {'count': 0}

    def fake_post_json(url: str, payload: dict, *, operation: str):
        calls['count'] += 1
        raise PromptWorkflowError(
            'Workflow request failed: unauthorized',
            operation='template_init',
            url=url,
            request_payload=payload,
            response_status=401,
            response_text='unauthorized',
        )

    monkeypatch.setattr('backend.services.prompt_workflows._post_json', fake_post_json)

    with pytest.raises(PromptWorkflowError, match='unauthorized'):
        initialize_prompt_template(
            item_id='itm_test',
            title='Midnight Noodles',
            model='Image generation prompt',
            source_language='en',
            raw_text=RAW_PROMPT,
        )

    assert calls['count'] == 1

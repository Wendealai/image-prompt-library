from pathlib import Path

from fastapi.testclient import TestClient

from backend.db import connect
from backend.main import create_app
from backend.repositories import ItemRepository, new_id, now
from backend.schemas import ItemCreate, ItemUpdate, PromptIn, PromptRenderSegment, PromptTemplateSlot, PromptVariantValue
from backend.services.prompt_markup import render_marked_text
from backend.services.prompt_workflows import PromptWorkflowError


MARKED_TEXT = 'A cinematic poster of [[slot id="main_subject" group="theme_core" label="主体"]]a tiny ramen bar[[/slot]] with [[slot id="support_props" group="theme_core" label="配套元素"]]paper lanterns and wooden stools[[/slot]].'


def _create_item(repo: ItemRepository) -> str:
    item = repo.create_item(ItemCreate(
        title='Midnight Noodles',
        prompts=[PromptIn(language='en', text='A cinematic poster of a tiny ramen bar with paper lanterns and wooden stools.', is_primary=True)],
    ))
    return item.id


def _create_named_item(repo: ItemRepository, title: str, prompt_text: str) -> str:
    item = repo.create_item(ItemCreate(
        title=title,
        prompts=[PromptIn(language='en', text=prompt_text, is_primary=True)],
    ))
    return item.id


def _mark_first_word(raw_text: str) -> str:
    first_word, rest = raw_text.split(' ', 1)
    return f'[[slot id="main_subject" group="theme_core" label="主体"]]{first_word}[[/slot]] {rest}'


def test_prompt_template_init_generate_reroll_and_accept(tmp_path: Path, monkeypatch):
    app = create_app(library_path=tmp_path / 'library')
    client = TestClient(app)
    repo = ItemRepository(tmp_path / 'library')
    item_id = _create_item(repo)

    def fake_init_prompt_template(**kwargs):
        assert kwargs['item_id'] == item_id
        assert kwargs['source_language'] == 'en'
        return {
            'marked_text': MARKED_TEXT,
            'analysis_confidence': 0.91,
            'analysis_notes': 'Looks stable.',
            'source_language': 'en',
        }

    responses = iter([
        {
            'slot_values': [
                {'slot_id': 'main_subject', 'text': 'a retro cassette store'},
                {'slot_id': 'support_props', 'text': 'neon price tags and stacked speakers'},
            ],
            'change_summary': 'Shifted the core theme from food to music retail.',
        },
        {
            'slot_values': [
                {'slot_id': 'main_subject', 'text': 'a midnight flower kiosk'},
                {'slot_id': 'support_props', 'text': 'glowing glass vases and folded wrapping paper'},
            ],
            'change_summary': 'Moved the scene toward a floral night market.',
        },
    ])

    def fake_generate_prompt_variant(**kwargs):
        return next(responses)

    monkeypatch.setattr('backend.routers.prompt_templates.initialize_prompt_template', fake_init_prompt_template)
    monkeypatch.setattr('backend.routers.prompt_templates.generate_prompt_variant', fake_generate_prompt_variant)

    init_response = client.post(f'/api/items/{item_id}/prompt-template/init', json={})
    assert init_response.status_code == 200
    init_payload = init_response.json()
    assert init_payload['template']['status'] == 'ready'
    assert init_payload['template']['slots'][0]['id'] == 'main_subject'
    assert init_payload['template']['analysis_confidence'] == 0.91

    template_id = init_payload['template']['id']
    generate_response = client.post(f'/api/templates/{template_id}/generate', json={'theme_keyword': 'retro music shop'})
    assert generate_response.status_code == 200
    session_payload = generate_response.json()
    assert session_payload['theme_keyword'] == 'retro music shop'
    assert session_payload['variants'][0]['iteration'] == 1
    assert session_payload['variants'][0]['rendered_text'] == 'A cinematic poster of a retro cassette store with neon price tags and stacked speakers.'
    assert any(segment['changed'] for segment in session_payload['variants'][0]['segments'])

    reroll_response = client.post(
        f"/api/generation-sessions/{session_payload['id']}/reroll",
        json={'rejected_variant_ids': [session_payload['variants'][0]['id']]},
    )
    assert reroll_response.status_code == 200
    reroll_payload = reroll_response.json()
    assert [variant['iteration'] for variant in reroll_payload['variants']] == [2, 1]
    assert reroll_payload['variants'][0]['rendered_text'] == 'A cinematic poster of a midnight flower kiosk with glowing glass vases and folded wrapping paper.'

    accept_response = client.post(f"/api/prompt-variants/{reroll_payload['variants'][0]['id']}/accept")
    assert accept_response.status_code == 200
    accepted_payload = accept_response.json()
    assert accepted_payload['accepted_variant_id'] == reroll_payload['variants'][0]['id']
    assert accepted_payload['variants'][0]['accepted'] is True


def test_prompt_template_init_prefers_simplified_source_when_traditional_is_auto_generated(tmp_path: Path, monkeypatch):
    app = create_app(library_path=tmp_path / 'library')
    client = TestClient(app)
    repo = ItemRepository(tmp_path / 'library')
    item = repo.create_item(ItemCreate(
        title='Soda Bottle',
        prompts=[PromptIn(language='zh_hans', text='红色 soda bottle on a steel table.', is_primary=True)],
    ))

    def fake_init_prompt_template(**kwargs):
        assert kwargs['source_language'] == 'zh_hans'
        return {
            'marked_text': _mark_first_word(kwargs['raw_text']),
            'analysis_confidence': 0.91,
            'analysis_notes': 'Uses the original simplified prompt.',
            'source_language': kwargs['source_language'],
        }

    monkeypatch.setattr('backend.routers.prompt_templates.initialize_prompt_template', fake_init_prompt_template)

    response = client.post(f'/api/items/{item.id}/prompt-template/init', json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload['template']['source_language'] == 'zh_hans'
    assert payload['template']['raw_text_snapshot'] == '红色 soda bottle on a steel table.'


def test_updating_prompts_marks_template_stale_and_clears_sessions(tmp_path: Path):
    repo = ItemRepository(tmp_path / 'library')
    item_id = _create_item(repo)
    template = repo.save_prompt_template(
        item_id=item_id,
        source_language='en',
        raw_text_snapshot='A cinematic poster of a tiny ramen bar with paper lanterns and wooden stools.',
        marked_text=MARKED_TEXT,
        slots=[
            PromptTemplateSlot(id='main_subject', group='theme_core', label='主体', original_text='a tiny ramen bar'),
            PromptTemplateSlot(id='support_props', group='theme_core', label='配套元素', original_text='paper lanterns and wooden stools'),
        ],
        analysis_confidence=0.8,
        analysis_notes='Stable',
    )
    session = repo.create_prompt_generation_session(template.id, 'retro music shop')
    repo.add_prompt_generation_variant(
        session.id,
        rendered_text='A cinematic poster of a retro cassette store with neon price tags and stacked speakers.',
        slot_values=[
            PromptVariantValue(slot_id='main_subject', text='a retro cassette store'),
            PromptVariantValue(slot_id='support_props', text='neon price tags and stacked speakers'),
        ],
        segments=[
            PromptRenderSegment(type='fixed', text='A cinematic poster of ', changed=False),
            PromptRenderSegment(type='slot', text='a retro cassette store', changed=True, slot_id='main_subject', label='主体', group='theme_core', before='a tiny ramen bar'),
        ],
        change_summary='Changed the scene.',
    )

    repo.update_item(item_id, ItemUpdate(
        prompts=[PromptIn(language='en', text='A cinematic poster of a tiny ramen bar at dawn with paper lanterns and wooden stools.', is_primary=True)],
    ))

    bundle = repo.get_prompt_template_bundle(item_id)
    assert bundle.template is not None
    assert bundle.template.status == 'stale'
    assert bundle.sessions == []


def test_bulk_prompt_template_init_processes_missing_templates_only(tmp_path: Path, monkeypatch):
    app = create_app(library_path=tmp_path / 'library')
    client = TestClient(app)
    repo = ItemRepository(tmp_path / 'library')
    missing_item_id = _create_named_item(repo, 'Paper Lanterns', 'Paper lanterns above a narrow alley.')
    ready_item_id = _create_named_item(repo, 'Glass Greenhouse', 'Glass greenhouse with orchids and mist.')
    existing_template = repo.save_prompt_template(
        item_id=ready_item_id,
        source_language='en',
        raw_text_snapshot='Glass greenhouse with orchids and mist.',
        marked_text=_mark_first_word('Glass greenhouse with orchids and mist.'),
        slots=[PromptTemplateSlot(id='main_subject', group='theme_core', label='主体', original_text='Glass')],
        analysis_confidence=0.8,
        analysis_notes='Already reviewed.',
    )
    initialized_ids: list[str] = []

    def fake_init_prompt_template(**kwargs):
        initialized_ids.append(kwargs['item_id'])
        return {
            'marked_text': _mark_first_word(kwargs['raw_text']),
            'analysis_confidence': 0.93,
            'analysis_notes': 'Bulk initialized.',
            'source_language': kwargs['source_language'],
        }

    monkeypatch.setattr('backend.routers.prompt_templates.initialize_prompt_template', fake_init_prompt_template)

    response = client.post('/api/prompt-templates/bulk-init', json={'mode': 'missing', 'limit': 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload['total_candidates'] == 1
    assert payload['processed_count'] == 1
    assert payload['failed_count'] == 0
    assert initialized_ids == [missing_item_id]
    assert payload['results'][0]['item_id'] == missing_item_id
    assert payload['results'][0]['slot_count'] == 1
    assert repo.get_prompt_template_bundle(missing_item_id).template is not None
    assert repo.get_prompt_template_bundle(ready_item_id).template.id == existing_template.id


def test_bulk_prompt_template_init_retries_simplified_prompt_after_workflow_error(tmp_path: Path, monkeypatch):
    app = create_app(library_path=tmp_path / 'library')
    client = TestClient(app)
    repo = ItemRepository(tmp_path / 'library')
    item = repo.create_item(ItemCreate(
        title='Future Runner',
        prompts=[PromptIn(language='en', text='A long cinematic runner poster with layered city reflections.', is_primary=True)],
    ))
    with connect(tmp_path / 'library') as conn:
        ts = now()
        conn.execute(
            "INSERT INTO prompts(id,item_id,language,text,is_primary,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (new_id('prm'), item.id, 'zh_hans', '未来跑者 poster with layered city reflections.', 0, ts, ts),
        )
        conn.commit()
    seen_languages: list[str] = []

    def fake_init_prompt_template(**kwargs):
        seen_languages.append(kwargs['source_language'])
        if kwargs['source_language'] == 'en':
            raise PromptWorkflowError('markedText must contain at least one slot marker.')
        return {
            'marked_text': _mark_first_word(kwargs['raw_text']),
            'analysis_confidence': 0.89,
            'analysis_notes': 'Retried with simplified source.',
            'source_language': kwargs['source_language'],
        }

    monkeypatch.setattr('backend.routers.prompt_templates.initialize_prompt_template', fake_init_prompt_template)

    response = client.post('/api/prompt-templates/bulk-init', json={'mode': 'missing', 'limit': 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload['processed_count'] == 1
    assert payload['failed_count'] == 0
    assert seen_languages == ['en', 'zh_hans']
    assert repo.get_prompt_template_bundle(item.id).template.source_language == 'zh_hans'


def test_bulk_prompt_template_init_uses_json_value_fallback_after_workflow_errors(tmp_path: Path, monkeypatch):
    app = create_app(library_path=tmp_path / 'library')
    client = TestClient(app)
    repo = ItemRepository(tmp_path / 'library')
    raw_prompt = '{\n  "style": "cinematic poster",\n  "subject": "red and blue high heels"\n}'
    item = repo.create_item(ItemCreate(
        title='Structured Prompt',
        prompts=[PromptIn(language='en', text=raw_prompt, is_primary=True)],
    ))

    def fake_init_prompt_template(**kwargs):
        raise PromptWorkflowError('markedText does not render back to the original prompt exactly.')

    monkeypatch.setattr('backend.routers.prompt_templates.initialize_prompt_template', fake_init_prompt_template)

    response = client.post('/api/prompt-templates/bulk-init', json={'mode': 'missing', 'limit': 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload['processed_count'] == 1
    assert payload['failed_count'] == 0
    template = repo.get_prompt_template_bundle(item.id).template
    assert template.source_language == 'en'
    assert template.raw_text_snapshot == raw_prompt
    assert 'group="structured_json"' in template.marked_text
    assert [slot.original_text for slot in template.slots] == ['cinematic poster', 'red and blue high heels']


def test_bulk_prompt_template_init_uses_plain_text_fallback_after_workflow_errors(tmp_path: Path, monkeypatch):
    app = create_app(library_path=tmp_path / 'library')
    client = TestClient(app)
    repo = ItemRepository(tmp_path / 'library')
    raw_prompt = (
        'Create a research poster for a multimodal AI workflow.\n'
        'Use a clean lab aesthetic with labeled arrows and compact captions.\n\n'
        'Show data entering the model, a reasoning trace, and a final visual answer.'
    )
    item = repo.create_item(ItemCreate(
        title='Workflow Poster',
        prompts=[PromptIn(language='en', text=raw_prompt, is_primary=True)],
    ))

    def fake_init_prompt_template(**kwargs):
        raise PromptWorkflowError('markedText does not render back to the original prompt exactly.')

    monkeypatch.setattr('backend.routers.prompt_templates.initialize_prompt_template', fake_init_prompt_template)

    response = client.post('/api/prompt-templates/bulk-init', json={'mode': 'missing', 'limit': 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload['processed_count'] == 1
    assert payload['failed_count'] == 0
    template = repo.get_prompt_template_bundle(item.id).template
    rendered_text, _segments = render_marked_text(template.marked_text)
    assert rendered_text == raw_prompt
    assert template.analysis_confidence == 0.55
    assert [slot.group for slot in template.slots] == ['content_block', 'content_block']


def test_bulk_prompt_template_init_dry_run_does_not_call_workflow(tmp_path: Path, monkeypatch):
    app = create_app(library_path=tmp_path / 'library')
    client = TestClient(app)
    repo = ItemRepository(tmp_path / 'library')
    item_id = _create_named_item(repo, 'Ceramic Market', 'Ceramic market stall under warm string lights.')

    def fail_init_prompt_template(**kwargs):
        raise AssertionError('dry-run should not call n8n')

    monkeypatch.setattr('backend.routers.prompt_templates.initialize_prompt_template', fail_init_prompt_template)

    response = client.post('/api/prompt-templates/bulk-init', json={'mode': 'missing', 'dry_run': True})

    assert response.status_code == 200
    payload = response.json()
    assert payload['total_candidates'] == 1
    assert payload['processed_count'] == 0
    assert payload['skipped_count'] == 1
    assert payload['results'][0]['item_id'] == item_id
    assert payload['results'][0]['status'] == 'would_initialize'
    assert repo.get_prompt_template_bundle(item_id).template is None

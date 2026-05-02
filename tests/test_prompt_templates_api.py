import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.repositories import ItemRepository
from backend.schemas import ItemCreate, ItemUpdate, PromptIn, PromptRenderSegment, PromptTemplateSlot, PromptVariantValue
from backend.services.prompt_workflow_failures import record_prompt_workflow_failure
from backend.services.prompt_workflows import PromptWorkflowError, PromptWorkflowUnavailable


MARKED_TEXT = 'A cinematic poster of [[slot id="main_subject" group="theme_core" label="主体"]]a tiny ramen bar[[/slot]] with [[slot id="support_props" group="theme_core" label="配套元素"]]paper lanterns and wooden stools[[/slot]].'
ADMIN_PASSWORD = 'zwyy0323'


def _create_item(repo: ItemRepository) -> str:
    item = repo.create_item(ItemCreate(
        title='Midnight Noodles',
        prompts=[PromptIn(language='en', text='A cinematic poster of a tiny ramen bar with paper lanterns and wooden stools.', is_primary=True)],
    ))
    return item.id


def _admin_login(client: TestClient):
    response = client.post('/api/admin/auth/login', json={'password': ADMIN_PASSWORD})
    assert response.status_code == 200
    assert response.json()['authenticated'] is True


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

    _admin_login(client)

    init_response = client.post(f'/api/admin/items/{item_id}/prompt-template/init', json={})
    assert init_response.status_code == 200
    init_payload = init_response.json()
    assert init_payload['template']['status'] == 'ready'
    assert init_payload['template']['review_status'] == 'pending_review'
    assert init_payload['template']['slots'][0]['id'] == 'main_subject'
    assert init_payload['template']['analysis_confidence'] == 0.91

    template_id = init_payload['template']['id']
    public_before_review = client.get(f'/api/items/{item_id}/prompt-template')
    assert public_before_review.status_code == 200
    assert public_before_review.json()['template'] is None

    admin_bundle = client.get(f'/api/admin/items/{item_id}/prompt-template')
    assert admin_bundle.status_code == 200
    assert admin_bundle.json()['template']['review_status'] == 'pending_review'

    approve_response = client.post(f'/api/admin/prompt-templates/{template_id}/approve', json={'review_notes': 'Looks good.'})
    assert approve_response.status_code == 200
    assert approve_response.json()['review_status'] == 'approved'
    assert approve_response.json()['review_notes'] == 'Looks good.'

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
    assert bundle.template.review_status == 'pending_review'
    assert bundle.sessions == []


def test_public_prompt_template_endpoint_only_returns_approved_templates(tmp_path: Path):
    app = create_app(library_path=tmp_path / 'library')
    client = TestClient(app)
    repo = ItemRepository(tmp_path / 'library')
    item_id = _create_item(repo)
    template = repo.save_prompt_template(
        item_id=item_id,
        source_language='en',
        raw_text_snapshot='A cinematic poster of a tiny ramen bar with paper lanterns and wooden stools.',
        marked_text=MARKED_TEXT,
        slots=[
            PromptTemplateSlot(id='main_subject', group='theme_core', label='主体', original_text='a tiny ramen bar'),
        ],
        analysis_confidence=0.8,
        analysis_notes='Stable',
    )

    hidden_response = client.get(f'/api/items/{item_id}/prompt-template')
    assert hidden_response.status_code == 200
    assert hidden_response.json()['template'] is None

    repo.review_prompt_template(template.id, review_status='approved', review_notes='Ship it.')

    visible_response = client.get(f'/api/items/{item_id}/prompt-template')
    assert visible_response.status_code == 200
    assert visible_response.json()['template']['review_status'] == 'approved'

    _admin_login(client)

    reject_response = client.post(f'/api/admin/prompt-templates/{template.id}/reject', json={'review_notes': 'Needs better slots.'})
    assert reject_response.status_code == 200
    assert reject_response.json()['review_status'] == 'rejected'

    hidden_again = client.get(f'/api/items/{item_id}/prompt-template')
    assert hidden_again.status_code == 200
    assert hidden_again.json()['template'] is None


def test_prompt_template_init_failure_is_recorded_with_failure_id(tmp_path: Path, monkeypatch):
    app = create_app(library_path=tmp_path / 'library')
    client = TestClient(app)
    repo = ItemRepository(tmp_path / 'library')
    item_id = _create_item(repo)

    def fake_init_prompt_template(**_kwargs):
        raise PromptWorkflowError(
            'Workflow request failed: {"message":"Error in workflow"}',
            operation='template_init',
            url='https://n8n.example/webhook/image-prompt-library-template-init',
            request_payload={'item': {'id': item_id}, 'prompt': {'language': 'en'}},
            response_status=500,
            response_text='{"message":"Error in workflow"}',
        )

    monkeypatch.setattr('backend.routers.prompt_templates.initialize_prompt_template', fake_init_prompt_template)

    _admin_login(client)

    response = client.post(f'/api/admin/items/{item_id}/prompt-template/init', json={})
    assert response.status_code == 424
    failure_id = response.headers.get('x-prompt-workflow-failure-id')
    assert failure_id
    assert failure_id in response.json()['detail']

    failure_path = tmp_path / 'library' / '_diagnostics' / 'prompt-workflow-failures' / f'{failure_id}.json'
    assert failure_path.is_file()
    sample = json.loads(failure_path.read_text(encoding='utf-8'))
    assert sample['id'] == failure_id
    assert sample['operation'] == 'template_init'
    assert sample['error_class'] == 'PromptWorkflowError'
    assert sample['workflow']['response_status'] == 500
    assert sample['workflow']['url'] == 'https://n8n.example/webhook/image-prompt-library-template-init'


def test_prompt_template_init_unavailable_returns_424_json(tmp_path: Path, monkeypatch):
    app = create_app(library_path=tmp_path / 'library')
    client = TestClient(app)
    repo = ItemRepository(tmp_path / 'library')
    item_id = _create_item(repo)

    def fake_init_prompt_template(**_kwargs):
        raise PromptWorkflowUnavailable('Missing webhook URL')

    monkeypatch.setattr('backend.routers.prompt_templates.initialize_prompt_template', fake_init_prompt_template)

    _admin_login(client)

    response = client.post(f'/api/admin/items/{item_id}/prompt-template/init', json={})
    assert response.status_code == 424
    assert response.json()['detail'] == 'AI prompt workflow is not configured.'


def test_prompt_template_init_extracts_wrapped_prompt_body_before_workflow(tmp_path: Path, monkeypatch):
    app = create_app(library_path=tmp_path / 'library')
    client = TestClient(app)
    repo = ItemRepository(tmp_path / 'library')
    wrapped_prompt = (
        "Here's how to create your Whiteboard Animation style image.\n\n"
        "Use Google Nano Banana Pro or any other AI image generation model.\n\n"
        "Use this prompt: clean whiteboard animation style illustration of the person from the reference image, "
        "drawn as a simple black marker sketch on a pure white background."
    )
    extracted_prompt = (
        "clean whiteboard animation style illustration of the person from the reference image, "
        "drawn as a simple black marker sketch on a pure white background."
    )
    item_id = repo.create_item(ItemCreate(
        title='Whiteboard Portrait',
        prompts=[PromptIn(language='en', text=wrapped_prompt, is_primary=True)],
    )).id
    captured: dict[str, str] = {}

    def fake_init_prompt_template(**kwargs):
        captured['raw_text'] = kwargs['raw_text']
        return {
            'marked_text': '[[slot id="style_and_subject" group="theme_core" label="style"]]clean whiteboard animation style illustration of the person from the reference image, drawn as a simple black marker sketch on a pure white background.[[/slot]]',
            'analysis_confidence': 0.95,
            'analysis_notes': 'Stable wrapper split.',
            'source_language': 'en',
        }

    monkeypatch.setattr('backend.routers.prompt_templates.initialize_prompt_template', fake_init_prompt_template)

    _admin_login(client)

    response = client.post(f'/api/admin/items/{item_id}/prompt-template/init', json={})
    assert response.status_code == 200
    payload = response.json()
    assert captured['raw_text'] == extracted_prompt
    assert payload['template']['raw_text_snapshot'] == extracted_prompt
    assert payload['template']['analysis_notes'].startswith('Prompt body extracted via labelled_tail before skeletonization.')


def test_prompt_template_ops_list_reports_missing_ready_stale_and_no_prompt(tmp_path: Path):
    app = create_app(library_path=tmp_path / 'library')
    client = TestClient(app)
    repo = ItemRepository(tmp_path / 'library')

    missing_id = _create_item(repo)
    ready_id = _create_item(repo)
    stale_id = _create_item(repo)
    no_prompt_id = repo.create_item(ItemCreate(
        title='Blank Prompt Case',
        prompts=[PromptIn(language='en', text='   ', is_primary=True)],
    )).id

    repo.save_prompt_template(
        item_id=ready_id,
        source_language='en',
        raw_text_snapshot='A cinematic poster of a tiny ramen bar with paper lanterns and wooden stools.',
        marked_text=MARKED_TEXT,
        slots=[
            PromptTemplateSlot(id='main_subject', group='theme_core', label='主体', original_text='a tiny ramen bar'),
            PromptTemplateSlot(id='support_props', group='theme_core', label='配套元素', original_text='paper lanterns and wooden stools'),
        ],
        analysis_confidence=0.93,
        analysis_notes='Ready',
    )
    repo.save_prompt_template(
        item_id=stale_id,
        source_language='en',
        raw_text_snapshot='A cinematic poster of a tiny ramen bar with paper lanterns and wooden stools.',
        marked_text=MARKED_TEXT,
        slots=[
            PromptTemplateSlot(id='main_subject', group='theme_core', label='主体', original_text='a tiny ramen bar'),
        ],
        status='stale',
    )

    _admin_login(client)

    response = client.get('/api/admin/prompt-templates/ops/items?limit=20')
    assert response.status_code == 200
    payload = response.json()
    status_by_item = {item['item_id']: item['status'] for item in payload['items']}
    assert status_by_item[missing_id] == 'missing'
    assert status_by_item[ready_id] == 'ready'
    assert status_by_item[stale_id] == 'stale'
    assert status_by_item[no_prompt_id] == 'no_prompt'
    assert payload['status_counts']['missing'] >= 1
    assert payload['status_counts']['ready'] >= 1
    assert payload['status_counts']['stale'] >= 1
    assert payload['status_counts']['no_prompt'] >= 1

    filtered = client.get('/api/admin/prompt-templates/ops/items?status=missing&status=stale&limit=20')
    assert filtered.status_code == 200
    filtered_statuses = {item['status'] for item in filtered.json()['items']}
    assert filtered_statuses == {'missing', 'stale'}


def test_prompt_template_ops_list_compares_normalized_prompt_body_for_wrapper_cases(tmp_path: Path):
    app = create_app(library_path=tmp_path / 'library')
    client = TestClient(app)
    repo = ItemRepository(tmp_path / 'library')
    wrapped_prompt = (
        "Here's how to create your Whiteboard Animation style image.\n\n"
        "Use Google Nano Banana Pro or any other AI image generation model.\n\n"
        "Use this prompt: clean whiteboard animation style illustration of the person from the reference image, "
        "drawn as a simple black marker sketch on a pure white background."
    )
    extracted_prompt = (
        "clean whiteboard animation style illustration of the person from the reference image, "
        "drawn as a simple black marker sketch on a pure white background."
    )
    item_id = repo.create_item(ItemCreate(
        title='Whiteboard Portrait',
        prompts=[PromptIn(language='en', text=wrapped_prompt, is_primary=True)],
    )).id
    repo.save_prompt_template(
        item_id=item_id,
        source_language='en',
        raw_text_snapshot=extracted_prompt,
        marked_text='[[slot id="style_and_subject" group="theme_core" label="style"]]clean whiteboard animation style illustration of the person from the reference image, drawn as a simple black marker sketch on a pure white background.[[/slot]]',
        slots=[
            PromptTemplateSlot(
                id='style_and_subject',
                group='theme_core',
                label='style',
                original_text=extracted_prompt,
            ),
        ],
        analysis_confidence=0.95,
    )

    _admin_login(client)

    response = client.get('/api/admin/prompt-templates/ops/items?limit=20')
    assert response.status_code == 200
    item = next(entry for entry in response.json()['items'] if entry['item_id'] == item_id)
    assert item['status'] == 'ready'
    assert item['prompt_excerpt'] == extracted_prompt[:160]


def test_prompt_template_batch_init_returns_initialized_failed_and_skipped(tmp_path: Path, monkeypatch):
    app = create_app(library_path=tmp_path / 'library')
    client = TestClient(app)
    repo = ItemRepository(tmp_path / 'library')

    success_id = _create_item(repo)
    failure_id = _create_item(repo)
    ready_id = _create_item(repo)
    no_prompt_id = repo.create_item(ItemCreate(
        title='No Prompt Available',
        prompts=[PromptIn(language='en', text='', is_primary=True)],
    )).id

    repo.save_prompt_template(
        item_id=ready_id,
        source_language='en',
        raw_text_snapshot='A cinematic poster of a tiny ramen bar with paper lanterns and wooden stools.',
        marked_text=MARKED_TEXT,
        slots=[
            PromptTemplateSlot(id='main_subject', group='theme_core', label='主体', original_text='a tiny ramen bar'),
        ],
    )
    repo.save_prompt_template(
        item_id=failure_id,
        source_language='en',
        raw_text_snapshot='A cinematic poster of a tiny ramen bar with paper lanterns and wooden stools.',
        marked_text=MARKED_TEXT,
        slots=[
            PromptTemplateSlot(id='main_subject', group='theme_core', label='主体', original_text='a tiny ramen bar'),
        ],
        status='stale',
    )

    def fake_init_prompt_template(**kwargs):
        if kwargs['item_id'] == failure_id:
            raise PromptWorkflowError(
                'Workflow request failed: {"message":"bad item"}',
                operation='template_init',
                url='https://n8n.example/webhook/image-prompt-library-template-init',
                request_payload={'item': {'id': failure_id}},
                response_status=500,
                response_text='{"message":"bad item"}',
            )
        return {
            'marked_text': MARKED_TEXT,
            'analysis_confidence': 0.88,
            'analysis_notes': 'Batch ready.',
            'source_language': 'en',
        }

    monkeypatch.setattr('backend.routers.prompt_templates.initialize_prompt_template', fake_init_prompt_template)

    _admin_login(client)

    response = client.post('/api/admin/prompt-templates/ops/batch-init', json={
        'item_ids': [success_id, failure_id, ready_id, no_prompt_id],
        'limit': 10,
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload['total_candidates'] == 4
    assert payload['processed'] == 4
    assert payload['initialized'] == 1
    assert payload['failed'] == 1
    assert payload['skipped'] == 2

    results = {item['item_id']: item for item in payload['results']}
    assert results[success_id]['result'] == 'initialized'
    assert results[failure_id]['result'] == 'failed'
    assert results[failure_id]['failure_id']
    assert results[ready_id]['result'] == 'skipped'
    assert results[no_prompt_id]['result'] == 'skipped'

    failure_sample = tmp_path / 'library' / '_diagnostics' / 'prompt-workflow-failures' / f"{results[failure_id]['failure_id']}.json"
    assert failure_sample.is_file()


def test_prompt_template_failure_list_and_detail_endpoints(tmp_path: Path):
    app = create_app(library_path=tmp_path / 'library')
    client = TestClient(app)

    failure_id, _ = record_prompt_workflow_failure(
        library_path=tmp_path / 'library',
        operation='template_generate',
        exc=PromptWorkflowError(
            'Workflow request failed: timeout',
            operation='template_generate',
            url='https://n8n.example/webhook/image-prompt-library-template-generate',
            request_payload={'template': {'id': 'tpl_123'}},
            response_status=502,
            response_text='timeout',
        ),
        context={
            'item_id': 'itm_123',
            'template_id': 'tpl_123',
            'theme_keyword': 'night market',
        },
    )

    _admin_login(client)

    list_response = client.get('/api/admin/prompt-template-failures?limit=10')
    assert list_response.status_code == 200
    failures = list_response.json()['failures']
    assert failures[0]['id'] == failure_id
    assert failures[0]['item_id'] == 'itm_123'
    assert failures[0]['template_id'] == 'tpl_123'
    assert failures[0]['theme_keyword'] == 'night market'
    assert failures[0]['response_status'] == 502

    detail_response = client.get(f'/api/admin/prompt-template-failures/{failure_id}')
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail['id'] == failure_id
    assert detail['context']['item_id'] == 'itm_123'
    assert detail['workflow']['url'] == 'https://n8n.example/webhook/image-prompt-library-template-generate'
    assert 'PromptWorkflowError' in detail['traceback']


def test_admin_auth_session_login_logout_and_protected_routes(tmp_path: Path):
    app = create_app(library_path=tmp_path / 'library')
    client = TestClient(app)
    repo = ItemRepository(tmp_path / 'library')
    item_id = _create_item(repo)

    session_before = client.get('/api/admin/auth/session')
    assert session_before.status_code == 200
    assert session_before.json()['authenticated'] is False

    protected_before = client.get(f'/api/admin/items/{item_id}/prompt-template')
    assert protected_before.status_code == 401

    invalid_login = client.post('/api/admin/auth/login', json={'password': 'wrong-password'})
    assert invalid_login.status_code == 401

    _admin_login(client)

    session_after = client.get('/api/admin/auth/session')
    assert session_after.status_code == 200
    assert session_after.json()['authenticated'] is True

    protected_after = client.get(f'/api/admin/items/{item_id}/prompt-template')
    assert protected_after.status_code == 200

    logout = client.post('/api/admin/auth/logout')
    assert logout.status_code == 200
    assert logout.json()['authenticated'] is False

    protected_after_logout = client.get(f'/api/admin/items/{item_id}/prompt-template')
    assert protected_after_logout.status_code == 401

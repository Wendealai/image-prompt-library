from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.repositories import ItemRepository
from backend.schemas import ItemCreate, ItemUpdate, PromptIn, PromptRenderSegment, PromptTemplateSlot, PromptVariantValue


MARKED_TEXT = 'A cinematic poster of [[slot id="main_subject" group="theme_core" label="主体"]]a tiny ramen bar[[/slot]] with [[slot id="support_props" group="theme_core" label="配套元素"]]paper lanterns and wooden stools[[/slot]].'


def _create_item(repo: ItemRepository) -> str:
    item = repo.create_item(ItemCreate(
        title='Midnight Noodles',
        prompts=[PromptIn(language='en', text='A cinematic poster of a tiny ramen bar with paper lanterns and wooden stools.', is_primary=True)],
    ))
    return item.id


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

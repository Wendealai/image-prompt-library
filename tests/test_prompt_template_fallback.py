from backend.services.prompt_markup import render_marked_text, validate_marked_prompt
from backend.services.prompt_template_fallback import build_fallback_prompt_template


def test_fallback_marks_explicit_argument_and_bracket_placeholders():
    raw_text = (
        '{"theme": "{argument name=\\"school name\\" default=\\"SNSスクール\\"}", '
        '"subject": "[PRODUCT]", "accent": "[BRAND COLOR]"}'
    )

    fallback = build_fallback_prompt_template(raw_text, reason="workflow 500")
    slots = validate_marked_prompt(raw_text, fallback.marked_text)
    rendered, _segments = render_marked_text(fallback.marked_text)

    assert rendered == raw_text
    assert len(slots) == 3
    assert slots[0].label == "school name"
    assert slots[1].original_text == "[PRODUCT]"
    assert slots[2].original_text == "[BRAND COLOR]"
    assert "Deterministic explicit placeholder fallback" in fallback.analysis_notes


def test_fallback_uses_full_prompt_slot_when_no_stable_markers_exist():
    raw_text = "Create a cinematic campaign poster with layered mist, a lonely hero, and warm rim lighting."

    fallback = build_fallback_prompt_template(raw_text)
    slots = validate_marked_prompt(raw_text, fallback.marked_text)
    rendered, _segments = render_marked_text(fallback.marked_text)

    assert rendered == raw_text
    assert len(slots) == 1
    assert slots[0].id == "prompt_body"
    assert slots[0].original_text == raw_text
    assert fallback.analysis_confidence < 0.4

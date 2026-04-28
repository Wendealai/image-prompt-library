from __future__ import annotations

import re
from typing import Iterable

from backend.schemas import PromptRenderSegment, PromptTemplateSlot, PromptVariantValue

SLOT_PATTERN = re.compile(r"\[\[slot(?P<attrs>[^\]]*)\]\](?P<content>.*?)\[\[/slot\]\]", re.DOTALL)
ATTR_PATTERN = re.compile(r'([a-zA-Z_][\w-]*)="([^"]*)"')


class PromptMarkupError(ValueError):
    pass


def _parse_attrs(raw_attrs: str) -> dict[str, str]:
    return {key: value for key, value in ATTR_PATTERN.findall(raw_attrs or "")}


def extract_slots(marked_text: str) -> list[PromptTemplateSlot]:
    slots: list[PromptTemplateSlot] = []
    seen_ids: set[str] = set()
    for match in SLOT_PATTERN.finditer(marked_text):
        attrs = _parse_attrs(match.group("attrs"))
        slot_id = attrs.get("id", "").strip()
        if not slot_id:
            raise PromptMarkupError("Each [[slot]] block must include an id attribute.")
        if slot_id in seen_ids:
            raise PromptMarkupError(f"Duplicate slot id: {slot_id}")
        seen_ids.add(slot_id)
        slots.append(PromptTemplateSlot(
            id=slot_id,
            group=attrs.get("group", "content") or "content",
            label=attrs.get("label", slot_id) or slot_id,
            original_text=match.group("content"),
            role=attrs.get("role") or None,
            instruction=attrs.get("instruction") or None,
        ))
    return slots


def normalize_slot_values(raw_values: Iterable[PromptVariantValue | dict[str, str]], slots: Iterable[PromptTemplateSlot]) -> list[PromptVariantValue]:
    normalized: list[PromptVariantValue] = []
    seen_ids: set[str] = set()
    allowed_ids = [slot.id for slot in slots]
    for raw_value in raw_values:
        value = raw_value if isinstance(raw_value, PromptVariantValue) else PromptVariantValue.model_validate(raw_value)
        slot_id = value.slot_id.strip()
        if not slot_id:
            raise PromptMarkupError("Each slot value must include a slot_id.")
        if slot_id in seen_ids:
            raise PromptMarkupError(f"Duplicate slot value: {slot_id}")
        seen_ids.add(slot_id)
        if slot_id not in allowed_ids:
            raise PromptMarkupError(f"Unknown slot value id: {slot_id}")
        normalized.append(PromptVariantValue(slot_id=slot_id, text=value.text))
    missing = [slot_id for slot_id in allowed_ids if slot_id not in seen_ids]
    if missing:
        raise PromptMarkupError(f"Missing slot values for: {', '.join(missing)}")
    return normalized


def render_marked_text(marked_text: str, slot_values: Iterable[PromptVariantValue | dict[str, str]] | None = None) -> tuple[str, list[PromptRenderSegment]]:
    value_map = {
        value.slot_id: value.text
        for value in [
            raw if isinstance(raw, PromptVariantValue) else PromptVariantValue.model_validate(raw)
            for raw in (slot_values or [])
        ]
    }
    rendered_parts: list[str] = []
    segments: list[PromptRenderSegment] = []
    cursor = 0
    for match in SLOT_PATTERN.finditer(marked_text):
        fixed_text = marked_text[cursor:match.start()]
        if fixed_text:
            rendered_parts.append(fixed_text)
            segments.append(PromptRenderSegment(type="fixed", text=fixed_text, changed=False))
        attrs = _parse_attrs(match.group("attrs"))
        slot_id = attrs.get("id", "").strip()
        if not slot_id:
            raise PromptMarkupError("Each [[slot]] block must include an id attribute.")
        original_text = match.group("content")
        next_text = value_map.get(slot_id, original_text)
        rendered_parts.append(next_text)
        segments.append(PromptRenderSegment(
            type="slot",
            text=next_text,
            changed=next_text != original_text,
            slot_id=slot_id,
            label=attrs.get("label", slot_id) or slot_id,
            group=attrs.get("group", "content") or "content",
            before=original_text,
        ))
        cursor = match.end()
    tail_text = marked_text[cursor:]
    if tail_text:
        rendered_parts.append(tail_text)
        segments.append(PromptRenderSegment(type="fixed", text=tail_text, changed=False))
    return "".join(rendered_parts), segments


def validate_marked_prompt(raw_text: str, marked_text: str) -> list[PromptTemplateSlot]:
    slots = extract_slots(marked_text)
    if not slots:
        raise PromptMarkupError("The marked prompt must include at least one [[slot]] block.")
    rendered, _segments = render_marked_text(marked_text)
    if rendered != raw_text:
        raise PromptMarkupError("The marked prompt must render back to the original prompt text exactly.")
    return slots

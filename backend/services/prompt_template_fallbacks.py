from __future__ import annotations

import json
import re

from backend.schemas import PromptTemplateSlot
from backend.services.prompt_markup import validate_marked_prompt

JSON_VALUE_PATTERN = re.compile(r'(?P<prefix>:\s*)"(?P<inner>(?:\\.|[^"\\])*)"')
MAX_TEXT_BLOCK_SLOTS = 24


def build_json_value_template(raw_text: str) -> tuple[str, list[PromptTemplateSlot]]:
    json.loads(raw_text)
    slot_index = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal slot_index
        inner = match.group("inner")
        if not inner:
            return match.group(0)
        slot_index += 1
        slot_id = f"json_value_{slot_index:03d}"
        label = f"JSON value {slot_index:03d}"
        return f'{match.group("prefix")}"[[slot id="{slot_id}" group="structured_json" label="{label}"]]{inner}[[/slot]]"'

    marked_text = JSON_VALUE_PATTERN.sub(replace, raw_text)
    slots = validate_marked_prompt(raw_text, marked_text)
    return marked_text, slots


def build_plain_text_block_template(raw_text: str) -> tuple[str, list[PromptTemplateSlot]]:
    spans = _paragraph_spans(raw_text)
    if len(spans) <= 1:
        spans = _line_spans(raw_text)
    if not spans:
        raise ValueError("Plain text fallback requires non-empty prompt text.")

    spans = _cap_spans(spans, MAX_TEXT_BLOCK_SLOTS)
    marked_text = _wrap_spans(raw_text, spans)
    slots = validate_marked_prompt(raw_text, marked_text)
    return marked_text, slots


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    block_start: int | None = None
    block_end: int | None = None
    offset = 0

    for line in text.splitlines(keepends=True):
        no_newline = line.rstrip("\r\n")
        stripped = no_newline.strip()
        if stripped:
            leading = len(no_newline) - len(no_newline.lstrip())
            trailing = len(no_newline.rstrip())
            if block_start is None:
                block_start = offset + leading
            block_end = offset + trailing
        elif block_start is not None and block_end is not None:
            spans.append((block_start, block_end))
            block_start = None
            block_end = None
        offset += len(line)

    if block_start is not None and block_end is not None:
        spans.append((block_start, block_end))
    return [(start, end) for start, end in spans if end > start]


def _line_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        no_newline = line.rstrip("\r\n")
        if no_newline.strip():
            leading = len(no_newline) - len(no_newline.lstrip())
            trailing = len(no_newline.rstrip())
            spans.append((offset + leading, offset + trailing))
        offset += len(line)
    return [(start, end) for start, end in spans if end > start]


def _cap_spans(spans: list[tuple[int, int]], max_count: int) -> list[tuple[int, int]]:
    if len(spans) <= max_count:
        return spans

    capped: list[tuple[int, int]] = []
    for index in range(max_count):
        start_index = index * len(spans) // max_count
        end_index = (index + 1) * len(spans) // max_count
        chunk = spans[start_index:end_index]
        capped.append((chunk[0][0], chunk[-1][1]))
    return capped


def _wrap_spans(text: str, spans: list[tuple[int, int]]) -> str:
    parts: list[str] = []
    cursor = 0
    for slot_index, (start, end) in enumerate(spans, start=1):
        parts.append(text[cursor:start])
        slot_id = f"text_block_{slot_index:03d}"
        label = f"Text block {slot_index:03d}"
        parts.append(f'[[slot id="{slot_id}" group="content_block" label="{label}"]]')
        parts.append(text[start:end])
        parts.append("[[/slot]]")
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)

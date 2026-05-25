from __future__ import annotations

import re
from dataclasses import dataclass

from backend.services.prompt_markup import extract_slots, validate_marked_prompt


@dataclass(frozen=True)
class FallbackPromptTemplate:
    marked_text: str
    analysis_confidence: float
    analysis_notes: str


_ARGUMENT_PATTERN = re.compile(
    r"\{argument\s+name=(?P<quote>\\?[\"'])(?P<name>.+?)(?P=quote)\s+default=(?P<default_quote>\\?[\"'])(?P<default>.*?)(?P=default_quote)\}",
    re.IGNORECASE | re.DOTALL,
)
_BRACKET_PLACEHOLDER_PATTERN = re.compile(r"\[[A-Za-z][A-Za-z0-9_ /：:，,.-]{1,72}\]")
_CJK_BRACKET_PLACEHOLDER_PATTERN = re.compile(r"【[^】\n]{1,48}】")
_CURLY_PLACEHOLDER_PATTERN = re.compile(r"\{[A-Za-z][A-Za-z0-9_ -]{1,56}\}")


def _slot_attr(value: str) -> str:
    return value.replace("&", "and").replace('"', "'").replace("<", "").replace(">", "").strip()


def _slug(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    if not normalized:
        normalized = fallback
    if normalized[0].isdigit():
        normalized = f"v_{normalized}"
    return normalized[:48]


def _placeholder_label(text: str) -> str:
    argument_match = _ARGUMENT_PATTERN.fullmatch(text)
    if argument_match:
        return argument_match.group("name").replace("\\", "").strip() or "argument"
    stripped = text.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped[1:-1].strip() or "placeholder"
    if stripped.startswith("【") and stripped.endswith("】"):
        return stripped[1:-1].strip() or "placeholder"
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped[1:-1].strip() or "placeholder"
    return stripped[:48] or "placeholder"


def _iter_placeholder_matches(raw_text: str):
    occupied: list[tuple[int, int]] = []
    patterns = [
        _ARGUMENT_PATTERN,
        _BRACKET_PLACEHOLDER_PATTERN,
        _CJK_BRACKET_PLACEHOLDER_PATTERN,
        _CURLY_PLACEHOLDER_PATTERN,
    ]
    for pattern in patterns:
        for match in pattern.finditer(raw_text):
            start, end = match.span()
            if any(start < used_end and end > used_start for used_start, used_end in occupied):
                continue
            occupied.append((start, end))
            yield match


def _build_marked_text(raw_text: str, matches: list[re.Match[str]]) -> str:
    parts: list[str] = []
    cursor = 0
    used_ids: set[str] = set()
    for index, match in enumerate(sorted(matches, key=lambda item: item.start()), start=1):
        label = _placeholder_label(match.group(0))
        slot_id = _slug(label, f"variable_{index}")
        if slot_id in used_ids:
            slot_id = f"{slot_id}_{index}"
        used_ids.add(slot_id)
        parts.append(raw_text[cursor:match.start()])
        parts.append(
            f'[[slot id="{_slot_attr(slot_id)}" group="explicit_variable" label="{_slot_attr(label)}" '
            f'role="fallback" instruction="Keep the surrounding prompt structure; edit this explicit variable only."]]'
        )
        parts.append(match.group(0))
        parts.append("[[/slot]]")
        cursor = match.end()
    parts.append(raw_text[cursor:])
    return "".join(parts)


def build_fallback_prompt_template(raw_text: str, *, reason: str | None = None) -> FallbackPromptTemplate:
    normalized_text = raw_text.strip()
    if not normalized_text:
        raise ValueError("Cannot build a prompt template from empty prompt text.")
    matches = list(_iter_placeholder_matches(normalized_text))
    if matches:
        marked_text = _build_marked_text(normalized_text, matches)
        confidence = 0.52
        mode = f"explicit placeholder fallback ({len(matches)} slot(s))"
    else:
        marked_text = (
            '[[slot id="prompt_body" group="fallback" label="完整 Prompt" role="fallback" '
            'instruction="No stable variable markers were detected. Edit the full prompt as one conservative variable."]]'
            f"{normalized_text}"
            "[[/slot]]"
        )
        confidence = 0.28
        mode = "full-prompt fallback"
    validate_marked_prompt(normalized_text, marked_text)
    slot_count = len(extract_slots(marked_text))
    notes = f"Deterministic {mode} generated after AI skeleton workflow failed."
    if reason:
        notes = f"{notes} Original failure: {reason[:320]}"
    notes = f"{notes} Manual review recommended before publishing. Slots: {slot_count}."
    return FallbackPromptTemplate(
        marked_text=marked_text,
        analysis_confidence=confidence,
        analysis_notes=notes,
    )

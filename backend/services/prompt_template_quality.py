from __future__ import annotations

import re
from dataclasses import dataclass

from backend.schemas import PromptTemplateSlot


@dataclass(frozen=True)
class PromptTemplateQuality:
    score: float
    label: str
    reasons: list[str]


_PLACEHOLDER_PATTERNS = [
    re.compile(r"\{argument\s+name=", re.IGNORECASE),
    re.compile(r"\[[A-Za-z][A-Za-z0-9_ /：:，,.-]{1,72}\]"),
    re.compile(r"【[^】\n]{1,48}】"),
    re.compile(r"\{[A-Za-z][A-Za-z0-9_ -]{1,56}\}"),
]

_VARIABLE_TYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("text", ("text", "copy", "caption", "slogan", "headline", "title", "wording", "文字", "标题", "標題", "文案", "标语", "標語")),
    ("brand", ("brand", "logo", "product name", "公司", "品牌", "商标", "商標", "logo")),
    ("subject", ("main_subject", "subject", "hero", "character", "person", "people", "animal", "object", "product", "主体", "主體", "人物", "角色", "产品", "產品")),
    ("topic", ("topic", "theme", "concept", "idea", "content", "主题", "主題", "题材", "題材", "内容", "內容")),
    ("style", ("style", "aesthetic", "genre", "render", "medium", "风格", "風格", "画风", "畫風", "媒介")),
    ("color", ("color", "colour", "palette", "tone", "hue", "配色", "颜色", "顏色", "色彩", "色调", "色調")),
    ("composition", ("composition", "layout", "framing", "camera", "angle", "shot", "perspective", "pose", "构图", "構圖", "镜头", "鏡頭", "视角", "視角", "姿态", "姿態")),
    ("setting", ("setting", "scene", "location", "background", "environment", "place", "场景", "場景", "背景", "环境", "環境", "地点", "地點")),
    ("lighting", ("lighting", "light", "shadow", "glow", "illumination", "光线", "光線", "照明", "阴影", "陰影")),
    ("reference", ("reference", "ref", "source image", "image", "photo", "参考", "參考", "原图", "原圖", "照片")),
    ("material", ("material", "texture", "fabric", "surface", "材质", "材質", "纹理", "紋理", "质感", "質感")),
]

_INPUT_HINTS = {
    "topic": "输入新的主题词或内容方向。",
    "subject": "输入新的主体、角色或核心对象。",
    "style": "输入想保留或替换的风格描述。",
    "color": "输入新的主色、配色或色调。",
    "composition": "输入构图、镜头、姿态或画面布局要求。",
    "text": "输入需要出现在画面中的文字。",
    "brand": "输入品牌、Logo 或产品名称。",
    "setting": "输入场景、地点或背景环境。",
    "lighting": "输入光线、时间或氛围要求。",
    "reference": "输入参考对象、参考图关系或保留规则。",
    "material": "输入材质、纹理或表面质感。",
    "other": "输入替换内容；保持周围骨架不变。",
}


def _combined_slot_text(slot: PromptTemplateSlot) -> str:
    return " ".join(
        value
        for value in (
            slot.id,
            slot.group,
            slot.label,
            slot.role,
            slot.instruction,
            slot.original_text[:160],
        )
        if value
    ).lower()


def infer_slot_variable_type(slot: PromptTemplateSlot) -> str:
    existing = (slot.variable_type or "").strip().lower()
    if existing:
        return existing.replace("-", "_")
    haystack = _combined_slot_text(slot)
    for variable_type, keywords in _VARIABLE_TYPE_RULES:
        if any(keyword.lower() in haystack for keyword in keywords):
            return variable_type
    return "other"


def normalize_prompt_template_slot(slot: PromptTemplateSlot) -> PromptTemplateSlot:
    variable_type = infer_slot_variable_type(slot)
    input_hint = (slot.input_hint or "").strip() or _INPUT_HINTS.get(variable_type, _INPUT_HINTS["other"])
    return PromptTemplateSlot(
        **{
            **slot.model_dump(),
            "variable_type": variable_type,
            "input_hint": input_hint,
        }
    )


def normalize_prompt_template_slots(slots: list[PromptTemplateSlot]) -> list[PromptTemplateSlot]:
    return [normalize_prompt_template_slot(slot) for slot in slots]


def _has_explicit_placeholder(text: str) -> bool:
    return any(pattern.search(text) for pattern in _PLACEHOLDER_PATTERNS)


def _quality_label(score: float) -> str:
    if score >= 0.82:
        return "excellent"
    if score >= 0.66:
        return "good"
    if score >= 0.48:
        return "needs_review"
    return "weak"


def score_prompt_template(
    *,
    raw_text: str,
    marked_text: str,
    slots: list[PromptTemplateSlot],
    analysis_confidence: float | None = None,
) -> PromptTemplateQuality:
    normalized_raw = raw_text.strip()
    normalized_slots = normalize_prompt_template_slots(slots)
    raw_length = max(len(normalized_raw), 1)
    score = 0.34
    reasons: list[str] = []

    if len(normalized_raw) >= 180:
        score += 0.16
        reasons.append("原始 prompt 信息量充足。")
    elif len(normalized_raw) >= 80:
        score += 0.12
        reasons.append("原始 prompt 长度适中。")
    elif len(normalized_raw) < 40:
        score -= 0.08
        reasons.append("原始 prompt 偏短，骨架判断空间有限。")

    slot_count = len(normalized_slots)
    if slot_count == 0:
        score = 0.08
        reasons.append("没有识别到变量槽。")
    elif 2 <= slot_count <= 8:
        score += 0.20
        reasons.append("变量数量处在可复用区间。")
    elif slot_count == 1:
        score += 0.08
        reasons.append("仅识别到一个变量，复用粒度偏粗。")
    elif slot_count <= 16:
        score += 0.12
        reasons.append("变量较多，审核时需确认是否过度切分。")
    else:
        score += 0.04
        reasons.append("变量过多，建议人工复核骨架稳定性。")

    slot_text_length = sum(len(slot.original_text.strip()) for slot in normalized_slots)
    coverage = slot_text_length / raw_length
    if 0.05 <= coverage <= 0.55:
        score += 0.20
        reasons.append("变量覆盖比例健康，骨架与可变部分区分较清晰。")
    elif 0.55 < coverage <= 0.80:
        score += 0.08
        reasons.append("变量覆盖偏高，需要确认骨架没有被吞进变量。")
    elif coverage > 0.80:
        score -= 0.14
        reasons.append("变量覆盖过高，可能接近整段 prompt fallback。")
    else:
        score -= 0.06
        reasons.append("变量覆盖过低，可能漏掉可替换内容。")

    ids = [slot.id for slot in normalized_slots]
    labels = [slot.label.strip().lower() for slot in normalized_slots if slot.label.strip()]
    if len(ids) == len(set(ids)) and len(labels) == len(set(labels)):
        score += 0.07
        reasons.append("变量 ID 与标签无明显重复。")
    else:
        score -= 0.16
        reasons.append("变量 ID 或标签存在重复。")

    variable_types = {slot.variable_type or "other" for slot in normalized_slots}
    typed_slots = [slot for slot in normalized_slots if (slot.variable_type or "other") != "other"]
    if len(variable_types) >= 2:
        score += 0.08
        reasons.append("已区分多种变量类型，前端替换提示更明确。")
    if typed_slots:
        score += 0.04
    else:
        score -= 0.05
        reasons.append("变量类型均未能明确推断。")
    if {"subject", "topic"} & variable_types:
        score += 0.04
        reasons.append("已识别主体或主题变量。")

    if any(slot.group == "fallback" or slot.id == "prompt_body" for slot in normalized_slots):
        score -= 0.16
        reasons.append("包含整段 prompt fallback，发布前应重新拆骨架。")
    if any(slot.group == "explicit_variable" or _has_explicit_placeholder(slot.original_text) for slot in normalized_slots):
        score += 0.07
        reasons.append("显式占位符已被保留为变量。")
    if "[[slot" in marked_text and "[[/slot]]" in marked_text:
        score += 0.04

    if analysis_confidence is not None:
        bounded_confidence = min(1.0, max(0.0, float(analysis_confidence)))
        score += bounded_confidence * 0.12
        if bounded_confidence < 0.55:
            reasons.append("AI/回退分析置信度偏低。")

    bounded_score = round(min(1.0, max(0.0, score)), 2)
    return PromptTemplateQuality(
        score=bounded_score,
        label=_quality_label(bounded_score),
        reasons=reasons[:8],
    )

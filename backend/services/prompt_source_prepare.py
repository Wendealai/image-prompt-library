from __future__ import annotations

from dataclasses import dataclass
import re

_CUE_LABEL_PATTERN = (
    r"(?:use this prompt|prompt to use|copy(?: and paste)?(?: this| the)? prompt|"
    r"try(?: out)?(?: this| the)? prompt|here(?:'s| is) the prompt|"
    r"please use the following prompt|use the following prompt|prompt text|prompt|"
    r"提示词(?:如下)?|请使用以下提示词|使用以下提示词|以下提示词|"
    r"使用这个提示词|使用这个prompt|用这个prompt|咒语(?:如下)?|文生图提示词)"
)

_LABELLED_CODE_BLOCK_RE = re.compile(
    rf"(?is)(?:^|\n{{2,}}|\n)\s*(?:{_CUE_LABEL_PATTERN})\s*(?:[:：]\s*|\n+)\s*```(?:[\w-]+)?\n(?P<body>.*?)```",
)
_LABELLED_TAIL_RE = re.compile(
    rf"(?is)(?:^|\n{{2,}}|\n)\s*(?:{_CUE_LABEL_PATTERN})\s*(?:[:：]\s*|\n+)(?P<body>.+?)\s*$",
)

_WRAPPER_HINT_RE = re.compile(
    r"(?is)\b(here(?:'s| is) how|use (?:google|chatgpt|nano banana|gpt)|reference image|"
    r"copy(?: and paste)?|upload|instruction|workflow|template|model)\b|"
    r"(步骤|使用|上传|模型|参考图|说明|教程|工作流)",
)


@dataclass(frozen=True)
class PreparedPromptSource:
    original_text: str
    normalized_text: str
    was_extracted: bool = False
    strategy: str = "original"


def _normalize_source_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _is_substantial_prompt_text(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) >= 60:
        return True
    word_count = len(re.findall(r"[A-Za-z0-9_]+", compact))
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", compact))
    return word_count >= 10 or cjk_count >= 14


def _pick_labelled_candidate(text: str) -> tuple[str, str] | None:
    for pattern, strategy in (
        (_LABELLED_CODE_BLOCK_RE, "labelled_code_block"),
        (_LABELLED_TAIL_RE, "labelled_tail"),
    ):
        matches = list(pattern.finditer(text))
        for match in reversed(matches):
            candidate = _normalize_source_text(match.group("body"))
            if _is_substantial_prompt_text(candidate):
                return candidate, strategy
    return None


def _pick_trailing_paragraph_candidate(text: str) -> tuple[str, str] | None:
    paragraphs = [_normalize_source_text(part) for part in re.split(r"\n\s*\n", text) if _normalize_source_text(part)]
    if len(paragraphs) < 3:
        return None
    candidate = paragraphs[-1]
    if not _is_substantial_prompt_text(candidate):
        return None
    if len(candidate) < max(len(part) for part in paragraphs[:-1]) * 1.35:
        return None
    wrapper_context = "\n\n".join(paragraphs[:-1])
    if not _WRAPPER_HINT_RE.search(wrapper_context):
        return None
    return candidate, "trailing_paragraph"


def prepare_prompt_template_source(text: str) -> PreparedPromptSource:
    normalized = _normalize_source_text(text)
    if not normalized:
        return PreparedPromptSource(original_text="", normalized_text="")

    labelled = _pick_labelled_candidate(normalized)
    if labelled and labelled[0] != normalized:
        return PreparedPromptSource(
            original_text=normalized,
            normalized_text=labelled[0],
            was_extracted=True,
            strategy=labelled[1],
        )

    trailing = _pick_trailing_paragraph_candidate(normalized)
    if trailing and trailing[0] != normalized:
        return PreparedPromptSource(
            original_text=normalized,
            normalized_text=trailing[0],
            was_extracted=True,
            strategy=trailing[1],
        )

    return PreparedPromptSource(original_text=normalized, normalized_text=normalized)

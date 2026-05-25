from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from PIL import Image, UnidentifiedImageError

import httpx

from backend.config import default_link_import_skill_url
from backend.schemas import CaseIntakeFetchResult, CaseIntakeImageCandidate

USER_AGENT = "ImagePromptLibrary/0.1 (+https://github.com/wendealai/image-prompt-library)"
MAX_INTAKE_CHARS = 12_000
MAX_REMOTE_IMAGE_BYTES = 30 * 1024 * 1024
SKIP_TAGS = {"script", "style", "noscript", "svg"}
BLOCK_TAGS = {
    "title",
    "p",
    "div",
    "section",
    "article",
    "main",
    "header",
    "footer",
    "aside",
    "blockquote",
    "pre",
    "li",
    "ul",
    "ol",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}
SOCIAL_STATUS_HOSTS = {
    "x.com",
    "www.x.com",
    "mobile.x.com",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
}
SOCIAL_PROMPT_TITLE_PREFIXES = (
    "prompt share",
    "prompt idea",
    "prompt breakdown",
    "style share",
    "style prompt",
)
SOCIAL_STATUS_PROMPT_LABEL_RE = (
    r"^[^A-Za-z0-9\u3400-\u9fff]*"
    r"(?:english\s+prompt|prompt|提示詞|提示词)\s*[:：-]?\s*(.*)$"
)
SOCIAL_STATUS_TCO_RE = r"https://t\.co/[A-Za-z0-9]+"


def _normalize_line(value: str) -> str:
    return " ".join(unescape(value).split()).strip()


def _truncated_text(lines: list[str]) -> str:
    output: list[str] = []
    total = 0
    for line in lines:
        fragment = line if not output else f"\n{line}"
        if total + len(fragment) > MAX_INTAKE_CHARS:
            remaining = MAX_INTAKE_CHARS - total
            if remaining > 0:
                output.append(fragment[:remaining].rstrip())
            break
        output.append(fragment)
        total += len(fragment)
    return "".join(output).strip()


def _default_import_skill_note() -> str | None:
    skill_url = default_link_import_skill_url()
    if not skill_url:
        return None
    return f"Default import skill: {skill_url}"


def _merge_notes_with_default_import_skill(notes: str | None) -> str | None:
    normalized_notes = (notes or "").strip()
    skill_note = _default_import_skill_note()
    skill_url = default_link_import_skill_url()
    if not skill_note:
        return normalized_notes or None
    if skill_note in normalized_notes or (skill_url and skill_url in normalized_notes):
        return normalized_notes or None
    if not normalized_notes:
        return skill_note
    return f"{normalized_notes}\n{skill_note}"


@dataclass
class FetchedCaseImage:
    url: str
    final_url: str
    filename: str
    content_type: str
    data: bytes


@dataclass
class ExtractedImageCandidate:
    url: str
    source: str
    alt: str | None = None


class StructuredHtmlExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self._chunks: list[str] = []
        self._title_chunks: list[str] = []
        self.title = ""
        self.description = ""
        self.author = ""
        self.image_url = ""
        self.first_body_image_url = ""
        self.image_candidates: list[ExtractedImageCandidate] = []
        self._skip_depth = 0
        self._in_title = False

    def _append_image_candidate(self, url: str, source: str, alt: str | None = None) -> None:
        candidate = url.strip()
        if not candidate or candidate.startswith("data:"):
            return
        self.image_candidates.append(ExtractedImageCandidate(candidate, source, alt or None))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if lowered == "meta":
            metadata = {key.lower(): value or "" for key, value in attrs}
            name = metadata.get("name", "").lower()
            prop = metadata.get("property", "").lower()
            content = _normalize_line(metadata.get("content", ""))
            if not content:
                return
            if not self.description and (name == "description" or prop == "og:description"):
                self.description = content
            if not self.title and prop == "og:title":
                self.title = content
            if not self.author and (name == "author" or prop == "article:author"):
                self.author = content
            if prop == "og:image":
                self._append_image_candidate(content, "open_graph")
            if prop == "twitter:image" or name == "twitter:image":
                self._append_image_candidate(content, "twitter")
            if not self.image_url and content and prop in {"og:image", "twitter:image"}:
                self.image_url = content
            return
        if lowered == "img":
            metadata = {key.lower(): value or "" for key, value in attrs}
            source = metadata.get("src", "").strip()
            alt = _normalize_line(metadata.get("alt", ""))
            self._append_image_candidate(source, "body", alt)
            if not self.first_body_image_url and source and not source.startswith("data:"):
                self.first_body_image_url = source
            return
        if lowered == "title":
            self._flush_line()
            self._in_title = True
            return
        if lowered == "br":
            self._flush_line()
            return
        if lowered in BLOCK_TAGS:
            self._flush_line()

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if lowered == "title":
            self._in_title = False
            title = _normalize_line(" ".join(self._title_chunks))
            if title and not self.title:
                self.title = title
            self._title_chunks = []
            return
        if lowered in BLOCK_TAGS:
            self._flush_line()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self._title_chunks.append(text)
        else:
            self._chunks.append(text)

    def _flush_line(self) -> None:
        if not self._chunks:
            return
        line = _normalize_line(" ".join(self._chunks))
        self._chunks = []
        if not line:
            return
        if self.lines and self.lines[-1] == line:
            return
        self.lines.append(line)


def _validated_url(url: str) -> str:
    normalized = url.strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Please enter a valid http or https URL.")
    return normalized


def _filtered_body_lines(lines: Iterable[str], title: str, description: str) -> list[str]:
    skip = {value.lower() for value in (title, description) if value}
    result: list[str] = []
    for line in lines:
        normalized = line.strip()
        if not normalized:
            continue
        if normalized.lower() in skip:
            continue
        result.append(normalized)
    return result


def _build_intake_text(title: str, final_url: str, description: str, author: str, body_lines: list[str]) -> str:
    lines: list[str] = []
    merged_description = _merge_notes_with_default_import_skill(description)
    if title:
        lines.append(f"Title: {title}")
    lines.append(f"Source URL: {final_url}")
    if author:
        lines.append(f"Author: {author}")
    if merged_description:
        lines.append("Notes:")
        lines.append(merged_description)
    if body_lines:
        lines.append("")
        lines.extend(body_lines)
    return _truncated_text(lines)


def _social_status_id(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() not in SOCIAL_STATUS_HOSTS:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 3 and parts[1] == "status" and parts[2].isdigit():
        return parts[2]
    if len(parts) >= 4 and parts[0] == "i" and parts[1] == "web" and parts[2] == "status" and parts[3].isdigit():
        return parts[3]
    return None


def _social_status_text_lines(text: str) -> list[str]:
    cleaned_text = re.sub(SOCIAL_STATUS_TCO_RE, "", text).replace("\r", "")
    return [_normalize_line(line) for line in cleaned_text.split("\n") if _normalize_line(line)]


def _social_status_title(line: str | None) -> str | None:
    if not line:
        return None
    for prefix in SOCIAL_PROMPT_TITLE_PREFIXES:
        pattern = rf"^{re.escape(prefix)}\s*[:：-]\s*(.+)$"
        match = re.match(pattern, line, flags=re.IGNORECASE)
        if match:
            title = _normalize_line(match.group(1))
            return title or None
    if re.match(SOCIAL_STATUS_PROMPT_LABEL_RE, line, flags=re.IGNORECASE):
        return None
    if len(line) <= 120:
        return line
    return None


def _social_status_prompt_parts(text: str) -> tuple[str | None, str | None, str | None]:
    lines = _social_status_text_lines(text)
    if not lines:
        return None, None, None
    title = _social_status_title(lines[0])
    prompt_lines: list[str] = []
    note_lines: list[str] = []
    found_prompt = False
    for index, line in enumerate(lines):
        if title and index == 0:
            continue
        match = re.match(SOCIAL_STATUS_PROMPT_LABEL_RE, line, flags=re.IGNORECASE)
        if match:
            found_prompt = True
            inline_prompt = _normalize_line(match.group(1))
            if inline_prompt:
                prompt_lines.append(inline_prompt)
            continue
        if found_prompt:
            prompt_lines.append(line)
            continue
        note_lines.append(line)

    if not found_prompt and lines:
        note_lines = lines[1:] if title and len(lines) > 1 else []
        prompt_lines = [] if note_lines else lines
    prompt = "\n".join(prompt_lines).strip() or None
    notes = "\n".join(note_lines).strip() or None
    return title, prompt, notes


def _social_status_author(payload: dict) -> str | None:
    user = payload.get("user")
    if not isinstance(user, dict):
        return None
    name = _normalize_line(str(user.get("name") or ""))
    screen_name = _normalize_line(str(user.get("screen_name") or ""))
    if name and screen_name:
        return f"{name} (@{screen_name})"
    if name:
        return name
    if screen_name:
        return f"@{screen_name}"
    return None


def _social_status_final_url(payload: dict, fallback_status_id: str) -> str:
    user = payload.get("user")
    if isinstance(user, dict):
        screen_name = _normalize_line(str(user.get("screen_name") or ""))
        if screen_name:
            return f"https://x.com/{screen_name}/status/{fallback_status_id}"
    return f"https://x.com/i/web/status/{fallback_status_id}"


def _social_status_image_candidates(payload: dict) -> list[CaseIntakeImageCandidate]:
    resolved: list[CaseIntakeImageCandidate] = []
    seen: set[str] = set()
    candidate_groups = []
    photos = payload.get("photos")
    media_details = payload.get("mediaDetails")
    if isinstance(photos, list):
        candidate_groups.append((photos, "tweet_photo", "url"))
    if isinstance(media_details, list):
        candidate_groups.append((media_details, "tweet_media", "media_url_https"))
    for items, source, field in candidate_groups:
        for item in items:
            if not isinstance(item, dict):
                continue
            candidate_url = _resolved_candidate_url("", str(item.get(field) or ""))
            if not candidate_url or candidate_url in seen:
                continue
            seen.add(candidate_url)
            resolved.append(CaseIntakeImageCandidate(url=candidate_url, source=source, alt=None))
    return resolved


def _social_status_tags(payload: dict) -> list[str]:
    entities = payload.get("entities")
    if not isinstance(entities, dict):
        return []
    hashtags = entities.get("hashtags")
    if not isinstance(hashtags, list):
        return []
    return [_normalize_line(str(tag.get("text") or "")) for tag in hashtags if isinstance(tag, dict) and _normalize_line(str(tag.get("text") or ""))]


def _build_social_status_intake_text(
    *,
    title: str | None,
    final_url: str,
    author: str | None,
    tags: list[str],
    notes: str | None,
    prompt: str | None,
) -> str:
    lines: list[str] = []
    merged_notes = _merge_notes_with_default_import_skill(notes)
    if title:
        lines.append(f"Title: {title}")
    lines.append(f"Source URL: {final_url}")
    if author:
        lines.append(f"Author: {author}")
    if tags:
        lines.append(f"Tags: {', '.join(tags)}")
    if merged_notes:
        lines.append("Notes:")
        lines.append(merged_notes)
    if prompt:
        lines.append("")
        lines.append("English Prompt:")
        lines.append(prompt)
    return _truncated_text(lines)


def _fetch_social_status_intake(url: str, client: httpx.Client) -> CaseIntakeFetchResult | None:
    status_id = _social_status_id(url)
    if not status_id:
        return None
    try:
        response = client.get("https://cdn.syndication.twimg.com/tweet-result", params={"id": status_id, "token": "1"})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None

    final_url = _social_status_final_url(payload, status_id)
    author = _social_status_author(payload)
    title, prompt, notes = _social_status_prompt_parts(str(payload.get("text") or ""))
    tags = _social_status_tags(payload)
    image_candidates = _social_status_image_candidates(payload)
    image_url = image_candidates[0].url if image_candidates else None
    intake_text = _build_social_status_intake_text(
        title=title,
        final_url=final_url,
        author=author,
        tags=tags,
        notes=notes,
        prompt=prompt,
    )
    return CaseIntakeFetchResult(
        url=url,
        final_url=final_url,
        title=title,
        description=notes,
        author=author,
        image_url=image_url,
        image_candidates=image_candidates,
        intake_text=intake_text,
    )


def _resolved_candidate_url(base_url: str, candidate: str | None) -> str | None:
    if not candidate:
        return None
    resolved = urljoin(base_url, candidate.strip())
    parsed = urlparse(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return resolved


def _resolved_image_candidates(base_url: str, candidates: Iterable[ExtractedImageCandidate]) -> list[CaseIntakeImageCandidate]:
    resolved_candidates: list[CaseIntakeImageCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = _resolved_candidate_url(base_url, candidate.url)
        if not resolved or resolved in seen:
            continue
        seen.add(resolved)
        resolved_candidates.append(
            CaseIntakeImageCandidate(
                url=resolved,
                source=candidate.source,
                alt=candidate.alt,
            )
        )
    return resolved_candidates


def _image_content_type(url: str, response_content_type: str | None, detected_format: str | None) -> str:
    content_type = (response_content_type or "").split(";", 1)[0].strip().lower()
    if content_type.startswith("image/"):
        return content_type
    guessed, _ = mimetypes.guess_type(url)
    if guessed and guessed.startswith("image/"):
        return guessed
    if detected_format:
        return Image.MIME.get(detected_format.upper(), "image/png")
    return "image/png"


def _image_filename(url: str, content_type: str, detected_format: str | None) -> str:
    path_name = Path(urlparse(url).path).name.strip()
    if path_name:
        filename = path_name
    else:
        filename = "reference-image"
    if Path(filename).suffix:
        return filename
    guessed_ext = mimetypes.guess_extension(content_type) or ""
    if not guessed_ext and detected_format:
        guessed_ext = f".{detected_format.lower()}"
    return f"{filename}{guessed_ext or '.png'}"


def fetch_case_intake_from_url(url: str, client: httpx.Client | None = None) -> CaseIntakeFetchResult:
    normalized_url = _validated_url(url)
    owns_client = client is None
    http_client = client or httpx.Client(
        timeout=httpx.Timeout(10.0, connect=5.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        social_result = _fetch_social_status_intake(normalized_url, http_client)
        if social_result is not None:
            return social_result
        response = http_client.get(normalized_url)
        response.raise_for_status()
        extractor = StructuredHtmlExtractor()
        extractor.feed(response.text)
        extractor.close()
        body_lines = _filtered_body_lines(extractor.lines, extractor.title, extractor.description)
        image_candidates = _resolved_image_candidates(str(response.url), extractor.image_candidates)
        image_url = image_candidates[0].url if image_candidates else (
            _resolved_candidate_url(str(response.url), extractor.image_url)
            or _resolved_candidate_url(str(response.url), extractor.first_body_image_url)
        )
        intake_text = _build_intake_text(
            title=extractor.title,
            final_url=str(response.url),
            description=extractor.description,
            author=extractor.author,
            body_lines=body_lines,
        )
        return CaseIntakeFetchResult(
            url=normalized_url,
            final_url=str(response.url),
            title=extractor.title or None,
            description=extractor.description or None,
            author=extractor.author or None,
            image_url=image_url,
            image_candidates=image_candidates,
            intake_text=intake_text,
        )
    finally:
        if owns_client:
            http_client.close()


def fetch_case_image_from_url(url: str, client: httpx.Client | None = None) -> FetchedCaseImage:
    normalized_url = _validated_url(url)
    owns_client = client is None
    http_client = client or httpx.Client(
        timeout=httpx.Timeout(10.0, connect=5.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        response = http_client.get(normalized_url)
        response.raise_for_status()
        data = response.content
        if len(data) > MAX_REMOTE_IMAGE_BYTES:
            raise ValueError("Remote image is too large.")
        try:
            with Image.open(BytesIO(data)) as image:
                detected_format = image.format
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("Source URL did not return a valid image.") from exc
        content_type = _image_content_type(str(response.url), response.headers.get("content-type"), detected_format)
        if not content_type.startswith("image/"):
            raise ValueError("Source URL did not return a valid image.")
        filename = _image_filename(str(response.url), content_type, detected_format)
        return FetchedCaseImage(
            url=normalized_url,
            final_url=str(response.url),
            filename=filename,
            content_type=content_type,
            data=data,
        )
    finally:
        if owns_client:
            http_client.close()

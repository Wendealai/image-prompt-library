from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from backend.db import connect, init_db
from backend.repositories import ItemRepository, StoredImageInput
from backend.schemas import (
    CangheGalleryImportedItem,
    CangheGallerySyncFailure,
    CangheGallerySyncResponse,
    ItemCreate,
    PromptIn,
)
from backend.services.image_store import store_image
from backend.services.prompt_markup import validate_marked_prompt
from backend.services.prompt_source_prepare import prepare_prompt_template_source
from backend.services.prompt_workflows import initialize_prompt_template

CANGHE_SITE_URL = "https://gpt-image2.canghe.ai/#gallery"
CANGHE_CASES_URL = "https://gpt-image2.canghe.ai/cases.json"
CANGHE_REPOSITORY_URL = "https://github.com/freestylefly/awesome-gpt-image-2"
CANGHE_SOURCE_NAME = "gpt-image2.canghe.ai / awesome-gpt-image-2"
CANGHE_TAG = "canghe-gallery"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

X_STATUS_RE = re.compile(r"(?:x|twitter)\.com/(?:i/)?[^/?#]*/status/(\d+)", re.IGNORECASE)
X_I_STATUS_RE = re.compile(r"(?:x|twitter)\.com/i/status/(\d+)", re.IGNORECASE)
CANGHE_CASE_NOTE_RE = re.compile(r"Canghe gallery case id:\s*(\d+)", re.IGNORECASE)
DEDUPE_NOTE_KEY_RE = re.compile(r"\b(?:canghe_case|x_status|source_url|prompt_sha256):[^\s,]+")
CJK_RE = re.compile(r"[\u3400-\u9fff]")


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _case_id(value: Any) -> str:
    text = _clean_text(value)
    return text or hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def normalize_source_url(value: str | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        return text.rstrip("/")
    netloc = parsed.netloc.lower()
    if netloc == "twitter.com":
        netloc = "x.com"
    path = re.sub(r"/+$", "", parsed.path)
    return urlunparse((parsed.scheme.lower(), netloc, path, "", "", ""))


def extract_x_status_id(value: str | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    match = X_STATUS_RE.search(text) or X_I_STATUS_RE.search(text)
    return match.group(1) if match else None


def prompt_hash(value: str | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def case_dedupe_keys(case: dict[str, Any]) -> set[str]:
    keys = {f"canghe_case:{_case_id(case.get('id'))}"}
    source_url = normalize_source_url(_clean_text(case.get("sourceUrl")) or _clean_text(case.get("githubUrl")))
    if source_url:
        keys.add(f"source_url:{source_url}")
    status_id = extract_x_status_id(_clean_text(case.get("sourceUrl")))
    if status_id:
        keys.add(f"x_status:{status_id}")
    hashed_prompt = prompt_hash(_clean_text(case.get("prompt")))
    if hashed_prompt:
        keys.add(f"prompt_sha256:{hashed_prompt}")
    return keys


def _keys_from_existing_row(source_url: str | None, notes: str | None) -> set[str]:
    keys: set[str] = set()
    normalized_url = normalize_source_url(source_url)
    if normalized_url:
        keys.add(f"source_url:{normalized_url}")
    status_id = extract_x_status_id(source_url)
    if status_id:
        keys.add(f"x_status:{status_id}")
    for match in CANGHE_CASE_NOTE_RE.finditer(notes or ""):
        keys.add(f"canghe_case:{match.group(1)}")
    for match in DEDUPE_NOTE_KEY_RE.finditer(notes or ""):
        keys.add(match.group(0).strip())
    return keys


def collect_existing_dedupe_keys(library_path: Path | str) -> set[str]:
    init_db(library_path)
    keys: set[str] = set()
    with connect(library_path) as conn:
        for row in conn.execute("SELECT source_url, notes FROM items WHERE archived=0").fetchall():
            keys.update(_keys_from_existing_row(row["source_url"], row["notes"]))
        for row in conn.execute("SELECT text FROM prompts WHERE TRIM(text) <> ''").fetchall():
            hashed_prompt = prompt_hash(row["text"])
            if hashed_prompt:
                keys.add(f"prompt_sha256:{hashed_prompt}")
    return keys


def prompt_language(prompt: str) -> str:
    return "zh_hans" if CJK_RE.search(prompt) else "en"


def image_url_for_case(case: dict[str, Any]) -> str | None:
    image = _clean_text(case.get("image"))
    if not image:
        return None
    return urljoin("https://gpt-image2.canghe.ai/", image)


def _image_filename(case: dict[str, Any], image_url: str) -> str:
    path_name = Path(urlparse(image_url).path).name
    return path_name or f"canghe-case-{_case_id(case.get('id'))}.jpg"


def _unique_tags(case: dict[str, Any]) -> list[str]:
    tags: list[str] = [CANGHE_TAG, "awesome-gpt-image-2", "GPT Image 2"]
    for value in [case.get("category"), *(case.get("styles") or []), *(case.get("scenes") or [])]:
        text = _clean_text(value)
        if text:
            tags.append(text)
    return list(dict.fromkeys(tags))


def notes_for_case(case: dict[str, Any]) -> str:
    keys = ", ".join(sorted(case_dedupe_keys(case)))
    parts = [
        f"Imported from {CANGHE_SITE_URL}.",
        f"Canghe gallery case id: {_case_id(case.get('id'))}",
        f"Repository: {CANGHE_REPOSITORY_URL}",
    ]
    github_url = _clean_text(case.get("githubUrl"))
    image = _clean_text(case.get("image"))
    if github_url:
        parts.append(f"GitHub source: {github_url}")
    if image:
        parts.append(f"Original image path: {image}")
    parts.append(f"Dedupe keys: {keys}")
    return "\n".join(parts)


def item_payload_for_case(case: dict[str, Any]) -> ItemCreate:
    title = _clean_text(case.get("title")) or f"Canghe GPT Image 2 case {_case_id(case.get('id'))}"
    prompt = _clean_text(case.get("prompt")) or title
    source_url = _clean_text(case.get("sourceUrl")) or _clean_text(case.get("githubUrl"))
    return ItemCreate(
        title=title,
        slug=f"canghe-gpt-image-2-case-{_case_id(case.get('id'))}",
        model="GPT Image 2",
        media_type="image",
        source_name=CANGHE_SOURCE_NAME,
        source_url=source_url,
        author=_clean_text(case.get("sourceLabel")),
        cluster_name=_clean_text(case.get("category")) or "GPT Image 2",
        tags=_unique_tags(case),
        notes=notes_for_case(case),
        prompts=[PromptIn(language=prompt_language(prompt), text=prompt, is_primary=True)],
    )


def select_new_cases(cases: list[dict[str, Any]], existing_keys: set[str], max_imports: int | None = None) -> tuple[list[dict[str, Any]], int]:
    selected: list[dict[str, Any]] = []
    duplicate_count = 0
    seen_keys = set(existing_keys)
    for case in cases:
        keys = case_dedupe_keys(case)
        if keys & seen_keys:
            duplicate_count += 1
            seen_keys.update(keys)
            continue
        selected.append(case)
        seen_keys.update(keys)
        if max_imports is not None and len(selected) >= max_imports:
            break
    return selected, duplicate_count


def fetch_canghe_cases(source_url: str = CANGHE_CASES_URL, client: httpx.Client | None = None) -> dict[str, Any]:
    close_client = client is None
    http = client or httpx.Client(follow_redirects=True, timeout=45, headers={"User-Agent": USER_AGENT})
    try:
        response = http.get(source_url)
        response.raise_for_status()
        data = response.json()
    finally:
        if close_client:
            http.close()
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise ValueError("Canghe gallery cases.json has an unexpected shape.")
    return data


def _download_image(image_url: str, client: httpx.Client | None = None) -> bytes:
    close_client = client is None
    http = client or httpx.Client(follow_redirects=True, timeout=60, headers={"User-Agent": USER_AGENT})
    try:
        response = http.get(image_url)
        response.raise_for_status()
        return response.content
    finally:
        if close_client:
            http.close()


def _archive_legacy_no_image_duplicates(library_path: Path | str, repo: ItemRepository, case: dict[str, Any], created_item_id: str) -> int:
    case_id = _case_id(case.get("id"))
    title = _clean_text(case.get("title")) or ""
    patterns = [f"%#case-{case_id}%", f"%case-{case_id}%"]
    with connect(library_path) as conn:
        rows = conn.execute(
            """
            SELECT i.id
            FROM items i
            LEFT JOIN images img ON img.item_id = i.id
            WHERE i.archived=0
              AND i.id <> ?
              AND i.source_name = 'freestylefly/awesome-gpt-image-2'
              AND i.title = ?
              AND (i.notes LIKE ? OR i.notes LIKE ?)
            GROUP BY i.id
            HAVING COUNT(img.id) = 0
            """,
            (created_item_id, title, *patterns),
        ).fetchall()
    archived = 0
    for row in rows:
        repo.set_archived(row["id"], True)
        archived += 1
    return archived


def _initialize_template(repo: ItemRepository, item_id: str, *, approve_template: bool) -> str | None:
    item = repo.get_item(item_id)
    source_prompt = next((prompt for prompt in item.prompts if prompt.is_primary and prompt.text.strip()), None)
    source_prompt = source_prompt or next((prompt for prompt in item.prompts if prompt.text.strip()), None)
    if source_prompt is None:
        raise ValueError("Imported item does not have a usable prompt.")
    prepared = prepare_prompt_template_source(source_prompt.text)
    workflow_result = initialize_prompt_template(
        item_id=item.id,
        title=item.title,
        model=item.model,
        source_language=source_prompt.language,
        raw_text=prepared.normalized_text,
    )
    slots = validate_marked_prompt(prepared.normalized_text, workflow_result["marked_text"])
    template = repo.save_prompt_template(
        item_id=item.id,
        source_language=workflow_result["source_language"],
        raw_text_snapshot=prepared.normalized_text,
        marked_text=workflow_result["marked_text"],
        slots=slots,
        status="ready",
        analysis_confidence=workflow_result["analysis_confidence"],
        analysis_notes=workflow_result["analysis_notes"],
    )
    if approve_template:
        template = repo.review_prompt_template(template.id, review_status="approved", review_notes="Auto-approved after Canghe gallery sync.")
    return template.id


def sync_canghe_gallery(
    library_path: Path | str,
    *,
    source_url: str = CANGHE_CASES_URL,
    cases_payload: dict[str, Any] | None = None,
    dry_run: bool = False,
    max_imports: int | None = None,
    initialize_templates: bool = False,
    approve_templates: bool = False,
    image_fetcher: Callable[[str], bytes] | None = None,
) -> CangheGallerySyncResponse:
    init_db(library_path)
    payload = cases_payload or fetch_canghe_cases(source_url)
    cases = [case for case in payload.get("cases", []) if isinstance(case, dict)]
    existing_keys = collect_existing_dedupe_keys(library_path)
    candidates, duplicate_count = select_new_cases(cases, existing_keys, max_imports=max_imports)
    result = CangheGallerySyncResponse(
        source_url=source_url,
        source_total=int(payload.get("totalCases") or len(cases)),
        duplicate_count=duplicate_count,
        candidate_count=len(candidates),
        dry_run=dry_run,
        max_imports=max_imports,
    )
    if dry_run:
        result.imported_items = [
            CangheGalleryImportedItem(
                case_id=_case_id(case.get("id")),
                title=_clean_text(case.get("title")) or f"Canghe GPT Image 2 case {_case_id(case.get('id'))}",
                source_url=_clean_text(case.get("sourceUrl")) or _clean_text(case.get("githubUrl")),
                image_url=image_url_for_case(case),
            )
            for case in candidates
        ]
        return result

    repo = ItemRepository(library_path)
    fetch_image = image_fetcher or _download_image
    for case in candidates:
        case_id = _case_id(case.get("id"))
        title = _clean_text(case.get("title")) or f"Canghe GPT Image 2 case {case_id}"
        created = None
        try:
            created = repo.create_item(item_payload_for_case(case), imported=True)
            result.imported_count += 1
            image_url = image_url_for_case(case)
            if image_url:
                image_bytes = fetch_image(image_url)
                stored = store_image(library_path, image_bytes, _image_filename(case, image_url))
                repo.add_image(
                    created.id,
                    StoredImageInput(
                        stored.original_path,
                        stored.thumb_path,
                        stored.preview_path,
                        width=stored.width,
                        height=stored.height,
                        file_sha256=stored.file_sha256,
                        role="result_image",
                    ),
                )
                result.image_count += 1
            result.archived_duplicate_count += _archive_legacy_no_image_duplicates(library_path, repo, case, created.id)
            template_id = None
            if initialize_templates:
                template_id = _initialize_template(repo, created.id, approve_template=approve_templates)
                result.template_initialized_count += 1
                if approve_templates:
                    result.template_approved_count += 1
            result.imported_items.append(
                CangheGalleryImportedItem(
                    item_id=created.id,
                    case_id=case_id,
                    title=title,
                    source_url=created.source_url,
                    image_url=image_url_for_case(case),
                    template_id=template_id,
                )
            )
        except Exception as exc:  # noqa: BLE001
            stage = "template" if created and initialize_templates else "import"
            result.failures.append(CangheGallerySyncFailure(case_id=case_id, title=title, stage=stage, detail=str(exc)))
    return result

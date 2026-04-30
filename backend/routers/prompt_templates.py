from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from backend.repositories import ItemRepository
from backend.schemas import (
    PromptGenerationSessionRecord,
    PromptTemplateBulkInitItemResult,
    PromptTemplateBulkInitRequest,
    PromptTemplateBulkInitResult,
    PromptTemplateBundle,
    PromptTemplateGenerateRequest,
    PromptTemplateInitRequest,
    PromptTemplateRecord,
    PromptTemplateRerollRequest,
)
from backend.services.prompt_markup import PromptMarkupError, normalize_slot_values, render_marked_text, validate_marked_prompt
from backend.services.prompt_template_fallbacks import build_json_value_template, build_plain_text_block_template
from backend.services.text_normalize import to_traditional
from backend.services.prompt_workflows import PromptWorkflowError, PromptWorkflowUnavailable, generate_prompt_variant, initialize_prompt_template

router = APIRouter()


def repo(request: Request) -> ItemRepository:
    return ItemRepository(request.app.state.library_path)


def _normalize_theme_keyword(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Theme keyword is required.")
    return value


def _not_found(exc: KeyError):
    raise HTTPException(status_code=404, detail="Prompt template resource not found.") from exc


def _handle_workflow_error(exc: Exception):
    if isinstance(exc, PromptWorkflowUnavailable):
        raise HTTPException(status_code=503, detail="AI prompt workflow is not configured.") from exc
    if isinstance(exc, PromptWorkflowError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if isinstance(exc, PromptMarkupError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _selected_source_prompt(repository: ItemRepository, item_id: str, language: str | None):
    item = repository.get_item(item_id)
    usable_prompts = [prompt for prompt in item.prompts if prompt.text.strip()]
    if not usable_prompts:
        raise HTTPException(status_code=400, detail="This item does not have a usable prompt yet.")
    if language:
        for prompt in usable_prompts:
            if prompt.language == language:
                return item, prompt
        raise HTTPException(status_code=400, detail=f"Prompt language not found: {language}")
    primary_prompt = next((prompt for prompt in usable_prompts if prompt.is_primary), usable_prompts[0])
    simplified_prompt = next((prompt for prompt in usable_prompts if prompt.language == "zh_hans"), None)
    if primary_prompt.language == "zh_hant" and simplified_prompt and primary_prompt.text == to_traditional(simplified_prompt.text):
        return item, simplified_prompt
    return item, primary_prompt


def _initialize_template_for_item(repository: ItemRepository, item_id: str, language: str | None) -> PromptTemplateRecord:
    item, source_prompt = _selected_source_prompt(repository, item_id, language)
    workflow_result = initialize_prompt_template(
        item=item,
        source_language=source_prompt.language,
        raw_text=source_prompt.text,
    )
    slots = validate_marked_prompt(source_prompt.text, workflow_result["marked_text"])
    return repository.save_prompt_template(
        item_id=item.id,
        source_language=workflow_result["source_language"],
        raw_text_snapshot=source_prompt.text,
        marked_text=workflow_result["marked_text"],
        slots=slots,
        status="ready",
        analysis_confidence=workflow_result["analysis_confidence"],
        analysis_notes=workflow_result["analysis_notes"],
    )


def _save_json_value_fallback_template(repository: ItemRepository, item_id: str, language: str | None, previous_error: Exception) -> PromptTemplateRecord:
    item, source_prompt = _selected_source_prompt(repository, item_id, language)
    marked_text, slots = build_json_value_template(source_prompt.text)
    return repository.save_prompt_template(
        item_id=item.id,
        source_language=source_prompt.language,
        raw_text_snapshot=source_prompt.text,
        marked_text=marked_text,
        slots=slots,
        status="ready",
        analysis_confidence=0.65,
        analysis_notes=f"Deterministic JSON value skeleton fallback after n8n init failed: {previous_error}",
    )


def _save_plain_text_fallback_template(repository: ItemRepository, item_id: str, language: str | None, previous_error: Exception) -> PromptTemplateRecord:
    item, source_prompt = _selected_source_prompt(repository, item_id, language)
    marked_text, slots = build_plain_text_block_template(source_prompt.text)
    return repository.save_prompt_template(
        item_id=item.id,
        source_language=source_prompt.language,
        raw_text_snapshot=source_prompt.text,
        marked_text=marked_text,
        slots=slots,
        status="ready",
        analysis_confidence=0.55,
        analysis_notes=f"Deterministic plain-text block skeleton fallback after n8n init failed: {previous_error}",
    )


def _fallback_languages(language: str | None) -> tuple[str | None, ...]:
    return (language,) if language is not None else ("zh_hans", None)


def _initialize_template_for_item_with_local_fallback(
    repository: ItemRepository,
    item_id: str,
    language: str | None,
    previous_error: Exception,
) -> PromptTemplateRecord:
    for fallback_language in _fallback_languages(language):
        try:
            return _save_json_value_fallback_template(repository, item_id, fallback_language, previous_error)
        except HTTPException as fallback_exc:
            if fallback_exc.status_code != 400:
                raise
        except (PromptMarkupError, ValueError):
            continue

    for fallback_language in _fallback_languages(language):
        try:
            return _save_plain_text_fallback_template(repository, item_id, fallback_language, previous_error)
        except HTTPException as fallback_exc:
            if fallback_exc.status_code != 400:
                raise
        except (PromptMarkupError, ValueError):
            continue

    raise previous_error


def _initialize_template_for_item_with_bulk_fallback(repository: ItemRepository, item_id: str, language: str | None) -> PromptTemplateRecord:
    try:
        return _initialize_template_for_item(repository, item_id, language)
    except PromptWorkflowError as first_exc:
        if language is not None:
            return _initialize_template_for_item_with_local_fallback(repository, item_id, language, first_exc)
        retry_error: Exception | None = None
        try:
            return _initialize_template_for_item(repository, item_id, "zh_hans")
        except HTTPException as retry_exc:
            if retry_exc.status_code != 400:
                raise
            retry_error = retry_exc
        except PromptWorkflowError as retry_exc:
            retry_error = retry_exc
        return _initialize_template_for_item_with_local_fallback(
            repository,
            item_id,
            language,
            retry_error if isinstance(retry_error, PromptWorkflowError) else first_exc,
        )


@router.get("/items/{item_id}/prompt-template", response_model=PromptTemplateBundle)
def get_prompt_template(request: Request, item_id: str):
    try:
        return repo(request).get_prompt_template_bundle(item_id)
    except KeyError as exc:
        _not_found(exc)


@router.post("/items/{item_id}/prompt-template/init", response_model=PromptTemplateBundle)
def init_prompt_template(request: Request, item_id: str, payload: PromptTemplateInitRequest):
    repository = repo(request)
    try:
        template = _initialize_template_for_item(repository, item_id, payload.language)
        return repository.get_prompt_template_bundle(template.item_id)
    except KeyError as exc:
        _not_found(exc)
    except Exception as exc:  # noqa: BLE001
        _handle_workflow_error(exc)


@router.post("/prompt-templates/bulk-init", response_model=PromptTemplateBulkInitResult)
def bulk_init_prompt_templates(request: Request, payload: PromptTemplateBulkInitRequest):
    repository = repo(request)
    total_candidates = repository.count_prompt_template_init_candidates(payload.mode)
    candidates = repository.list_prompt_template_init_candidates(payload.mode, payload.limit)
    results: list[PromptTemplateBulkInitItemResult] = []
    if payload.dry_run:
        for candidate in candidates:
            results.append(PromptTemplateBulkInitItemResult(
                item_id=str(candidate["item_id"]),
                title=str(candidate["title"]),
                status="would_initialize",
                template_id=candidate["template_id"],
                detail=candidate["template_status"],
            ))
        return PromptTemplateBulkInitResult(
            mode=payload.mode,
            dry_run=True,
            total_candidates=total_candidates,
            skipped_count=len(results),
            results=results,
        )

    for candidate in candidates:
        item_id = str(candidate["item_id"])
        title = str(candidate["title"])
        try:
            template = _initialize_template_for_item_with_bulk_fallback(repository, item_id, payload.language)
            results.append(PromptTemplateBulkInitItemResult(
                item_id=item_id,
                title=title,
                status="initialized",
                template_id=template.id,
                slot_count=len(template.slots),
            ))
        except PromptWorkflowUnavailable as exc:
            _handle_workflow_error(exc)
        except Exception as exc:  # noqa: BLE001
            results.append(PromptTemplateBulkInitItemResult(
                item_id=item_id,
                title=title,
                status="failed",
                detail=str(exc),
            ))

    processed_count = sum(1 for result in results if result.status == "initialized")
    failed_count = sum(1 for result in results if result.status == "failed")
    return PromptTemplateBulkInitResult(
        mode=payload.mode,
        dry_run=False,
        total_candidates=total_candidates,
        processed_count=processed_count,
        failed_count=failed_count,
        results=results,
    )


@router.post("/templates/{template_id}/generate", response_model=PromptGenerationSessionRecord)
def generate_prompt_template_variant(request: Request, template_id: str, payload: PromptTemplateGenerateRequest):
    repository = repo(request)
    try:
        template = repository.get_prompt_template_by_id(template_id)
        item = repository.get_item(template.item_id)
        if template.status != "ready":
            raise HTTPException(status_code=409, detail="The prompt template must be re-initialized before generating variants.")
        theme_keyword = _normalize_theme_keyword(payload.theme_keyword)
        workflow_result = generate_prompt_variant(template=template, item=item, theme_keyword=theme_keyword, previous_variants=[])
        slot_values = normalize_slot_values(workflow_result["slot_values"], template.slots)
        rendered_text, segments = render_marked_text(template.marked_text, slot_values)
        session = repository.create_prompt_generation_session(template_id, theme_keyword)
        return repository.add_prompt_generation_variant(
            session.id,
            rendered_text=rendered_text,
            slot_values=slot_values,
            segments=segments,
            change_summary=workflow_result.get("change_summary"),
        )
    except KeyError as exc:
        _not_found(exc)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _handle_workflow_error(exc)


@router.post("/generation-sessions/{session_id}/reroll", response_model=PromptGenerationSessionRecord)
def reroll_prompt_template_variant(request: Request, session_id: str, payload: PromptTemplateRerollRequest):
    repository = repo(request)
    try:
        session = repository.get_prompt_generation_session(session_id)
        template = repository.get_prompt_template_by_id(session.template_id)
        item = repository.get_item(template.item_id)
        if template.status != "ready":
            raise HTTPException(status_code=409, detail="The prompt template must be re-initialized before generating variants.")
        rejected_ids = {variant_id for variant_id in payload.rejected_variant_ids if variant_id}
        previous_variants = [variant for variant in session.variants if not rejected_ids or variant.id in rejected_ids]
        workflow_result = generate_prompt_variant(template=template, item=item, theme_keyword=session.theme_keyword, previous_variants=previous_variants)
        slot_values = normalize_slot_values(workflow_result["slot_values"], template.slots)
        rendered_text, segments = render_marked_text(template.marked_text, slot_values)
        return repository.add_prompt_generation_variant(
            session.id,
            rendered_text=rendered_text,
            slot_values=slot_values,
            segments=segments,
            change_summary=workflow_result.get("change_summary"),
        )
    except KeyError as exc:
        _not_found(exc)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _handle_workflow_error(exc)


@router.post("/prompt-variants/{variant_id}/accept", response_model=PromptGenerationSessionRecord)
def accept_prompt_template_variant(request: Request, variant_id: str):
    try:
        return repo(request).accept_prompt_generation_variant(variant_id)
    except KeyError as exc:
        _not_found(exc)

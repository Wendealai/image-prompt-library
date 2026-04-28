from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from backend.repositories import ItemRepository
from backend.schemas import PromptGenerationSessionRecord, PromptTemplateBundle, PromptTemplateGenerateRequest, PromptTemplateInitRequest, PromptTemplateRerollRequest
from backend.services.prompt_markup import PromptMarkupError, normalize_slot_values, render_marked_text, validate_marked_prompt
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
    return item, primary_prompt


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
        item, source_prompt = _selected_source_prompt(repository, item_id, payload.language)
        workflow_result = initialize_prompt_template(
            item_id=item.id,
            title=item.title,
            model=item.model,
            source_language=source_prompt.language,
            raw_text=source_prompt.text,
        )
        slots = validate_marked_prompt(source_prompt.text, workflow_result["marked_text"])
        repository.save_prompt_template(
            item_id=item.id,
            source_language=workflow_result["source_language"],
            raw_text_snapshot=source_prompt.text,
            marked_text=workflow_result["marked_text"],
            slots=slots,
            status="ready",
            analysis_confidence=workflow_result["analysis_confidence"],
            analysis_notes=workflow_result["analysis_notes"],
        )
        return repository.get_prompt_template_bundle(item.id)
    except KeyError as exc:
        _not_found(exc)
    except Exception as exc:  # noqa: BLE001
        _handle_workflow_error(exc)


@router.post("/templates/{template_id}/generate", response_model=PromptGenerationSessionRecord)
def generate_prompt_template_variant(request: Request, template_id: str, payload: PromptTemplateGenerateRequest):
    repository = repo(request)
    try:
        template = repository.get_prompt_template_by_id(template_id)
        if template.status != "ready":
            raise HTTPException(status_code=409, detail="The prompt template must be re-initialized before generating variants.")
        theme_keyword = _normalize_theme_keyword(payload.theme_keyword)
        workflow_result = generate_prompt_variant(template=template, theme_keyword=theme_keyword, previous_variants=[])
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
        if template.status != "ready":
            raise HTTPException(status_code=409, detail="The prompt template must be re-initialized before generating variants.")
        rejected_ids = {variant_id for variant_id in payload.rejected_variant_ids if variant_id}
        previous_variants = [variant for variant in session.variants if not rejected_ids or variant.id in rejected_ids]
        workflow_result = generate_prompt_variant(template=template, theme_keyword=session.theme_keyword, previous_variants=previous_variants)
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

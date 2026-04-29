from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from backend.admin_auth import require_admin
from backend.repositories import ItemRepository
from backend.schemas import PromptGenerationSessionRecord, PromptTemplateBatchInitRequest, PromptTemplateBatchInitResponse, PromptTemplateBatchInitResult, PromptTemplateBundle, PromptTemplateGenerateRequest, PromptTemplateInitRequest, PromptTemplateOpsItemList, PromptTemplateRecord, PromptTemplateReviewRequest, PromptTemplateRerollRequest, PromptWorkflowFailureList, PromptWorkflowFailureRecord
from backend.services.prompt_workflow_failures import list_prompt_workflow_failures, read_prompt_workflow_failure, record_prompt_workflow_failure, summarize_prompt_workflow_failure
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


def _record_workflow_failure_sample(request: Request, exc: Exception, *, operation: str, context: dict | None = None) -> str | None:
    if not isinstance(exc, (PromptWorkflowError, PromptMarkupError, ValueError)):
        return None
    failure_id, _ = record_prompt_workflow_failure(
        library_path=request.app.state.library_path,
        operation=operation,
        exc=exc,
        context=context,
    )
    return failure_id


def _handle_workflow_error(request: Request, exc: Exception, *, operation: str, context: dict | None = None):
    if isinstance(exc, PromptWorkflowUnavailable):
        raise HTTPException(status_code=503, detail="AI prompt workflow is not configured.") from exc
    failure_id = _record_workflow_failure_sample(request, exc, operation=operation, context=context)
    headers: dict[str, str] | None = None
    if failure_id:
        headers = {"X-Prompt-Workflow-Failure-Id": failure_id}
    if isinstance(exc, PromptWorkflowError):
        detail = str(exc) if not failure_id else f"{exc} [failure_id={failure_id}]"
        raise HTTPException(status_code=502, detail=detail, headers=headers) from exc
    if isinstance(exc, PromptMarkupError):
        detail = str(exc) if not failure_id else f"{exc} [failure_id={failure_id}]"
        raise HTTPException(status_code=400, detail=detail, headers=headers) from exc
    if isinstance(exc, ValueError):
        detail = str(exc) if not failure_id else f"{exc} [failure_id={failure_id}]"
        raise HTTPException(status_code=400, detail=detail, headers=headers) from exc
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


def _initialize_prompt_template_bundle(repository: ItemRepository, *, item_id: str, language: str | None):
    workflow_result = None
    source_prompt = None
    item = None
    item, source_prompt = _selected_source_prompt(repository, item_id, language)
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
    return repository.get_prompt_template_bundle(item.id), item, source_prompt, workflow_result


@router.get("/items/{item_id}/prompt-template", response_model=PromptTemplateBundle)
def get_prompt_template(request: Request, item_id: str):
    try:
        return repo(request).get_prompt_template_bundle(item_id, public_only=True)
    except KeyError as exc:
        _not_found(exc)


@router.get("/admin/items/{item_id}/prompt-template", response_model=PromptTemplateBundle)
def get_admin_prompt_template(request: Request, item_id: str):
    require_admin(request)
    try:
        return repo(request).get_prompt_template_bundle(item_id)
    except KeyError as exc:
        _not_found(exc)


@router.post("/admin/items/{item_id}/prompt-template/init", response_model=PromptTemplateBundle)
def init_prompt_template(request: Request, item_id: str, payload: PromptTemplateInitRequest):
    require_admin(request)
    repository = repo(request)
    workflow_result = None
    source_prompt = None
    item = None
    try:
        bundle, item, source_prompt, workflow_result = _initialize_prompt_template_bundle(repository, item_id=item_id, language=payload.language)
        return bundle
    except KeyError as exc:
        _not_found(exc)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _handle_workflow_error(
            request,
            exc,
            operation="template_init",
            context={
                "item_id": item_id,
                "requested_language": payload.language,
                "item": item.model_dump() if item else None,
                "source_prompt": source_prompt.model_dump() if source_prompt else None,
                "workflow_result": workflow_result,
            },
        )


@router.post("/admin/prompt-templates/{template_id}/approve", response_model=PromptTemplateRecord)
def approve_prompt_template(request: Request, template_id: str, payload: PromptTemplateReviewRequest):
    require_admin(request)
    try:
        return repo(request).review_prompt_template(template_id, review_status="approved", review_notes=payload.review_notes)
    except KeyError as exc:
        _not_found(exc)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/admin/prompt-templates/{template_id}/reject", response_model=PromptTemplateRecord)
def reject_prompt_template(request: Request, template_id: str, payload: PromptTemplateReviewRequest):
    require_admin(request)
    try:
        return repo(request).review_prompt_template(template_id, review_status="rejected", review_notes=payload.review_notes)
    except KeyError as exc:
        _not_found(exc)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/admin/prompt-templates/ops/items", response_model=PromptTemplateOpsItemList)
def list_prompt_template_ops(
    request: Request,
    status: list[str] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=300),
):
    require_admin(request)
    return repo(request).list_prompt_template_ops_items(statuses=status, limit=limit)


@router.post("/admin/prompt-templates/ops/batch-init", response_model=PromptTemplateBatchInitResponse)
def batch_init_prompt_templates(request: Request, payload: PromptTemplateBatchInitRequest):
    require_admin(request)
    repository = repo(request)
    candidates = repository.list_prompt_template_ops_items(
        item_ids=payload.item_ids or None,
        statuses=None if payload.item_ids else payload.statuses,
        limit=payload.limit,
    ).items
    results: list[PromptTemplateBatchInitResult] = []
    initialized = 0
    skipped = 0
    failed = 0

    for candidate in candidates:
        if not candidate.can_initialize and not payload.force:
            skipped += 1
            results.append(PromptTemplateBatchInitResult(
                item_id=candidate.item_id,
                title=candidate.title,
                result="skipped",
                detail="Template is already ready." if candidate.status == "ready" else "This item does not have a usable prompt.",
                template_id=candidate.template_id,
                template_status=candidate.template_status or candidate.status,
                slot_count=candidate.slot_count,
            ))
            continue
        workflow_result = None
        source_prompt = None
        item = None
        try:
            bundle, item, source_prompt, workflow_result = _initialize_prompt_template_bundle(
                repository,
                item_id=candidate.item_id,
                language=payload.language,
            )
            template = bundle.template
            initialized += 1
            results.append(PromptTemplateBatchInitResult(
                item_id=candidate.item_id,
                title=candidate.title,
                result="initialized",
                detail="Template initialized.",
                template_id=template.id if template else None,
                template_status=template.status if template else None,
                slot_count=len(template.slots) if template else 0,
            ))
        except KeyError:
            failed += 1
            results.append(PromptTemplateBatchInitResult(
                item_id=candidate.item_id,
                title=candidate.title,
                result="failed",
                detail="Prompt template resource not found.",
            ))
        except HTTPException as exc:
            skipped += 1
            results.append(PromptTemplateBatchInitResult(
                item_id=candidate.item_id,
                title=candidate.title,
                result="skipped",
                detail=str(exc.detail),
                template_id=candidate.template_id,
                template_status=candidate.template_status or candidate.status,
                slot_count=candidate.slot_count,
            ))
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, PromptWorkflowUnavailable):
                _handle_workflow_error(
                    request,
                    exc,
                    operation="template_init",
                    context={
                        "item_id": candidate.item_id,
                    },
                )
            failure_id = _record_workflow_failure_sample(
                request,
                exc,
                operation="template_init",
                context={
                    "item_id": candidate.item_id,
                    "requested_language": payload.language,
                    "item": item.model_dump() if item else None,
                    "source_prompt": source_prompt.model_dump() if source_prompt else None,
                    "workflow_result": workflow_result,
                },
            )
            failed += 1
            detail = str(exc) if not failure_id else f"{exc} [failure_id={failure_id}]"
            results.append(PromptTemplateBatchInitResult(
                item_id=candidate.item_id,
                title=candidate.title,
                result="failed",
                detail=detail,
                failure_id=failure_id,
                template_id=candidate.template_id,
                template_status=candidate.template_status or candidate.status,
                slot_count=candidate.slot_count,
            ))

    return PromptTemplateBatchInitResponse(
        total_candidates=len(candidates),
        processed=len(results),
        initialized=initialized,
        skipped=skipped,
        failed=failed,
        results=results,
    )


@router.get("/admin/prompt-template-failures", response_model=PromptWorkflowFailureList)
def get_prompt_template_failures(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
):
    require_admin(request)
    failures = list_prompt_workflow_failures(request.app.state.library_path, limit=limit)
    return PromptWorkflowFailureList(failures=failures, total=len(failures), limit=limit)


@router.get("/admin/prompt-template-failures/{failure_id}", response_model=PromptWorkflowFailureRecord)
def get_prompt_template_failure(request: Request, failure_id: str):
    require_admin(request)
    try:
        payload = read_prompt_workflow_failure(request.app.state.library_path, failure_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Prompt workflow failure sample not found.") from exc
    return PromptWorkflowFailureRecord(
        **summarize_prompt_workflow_failure(payload),
        context=payload.get("context") if isinstance(payload.get("context"), dict) else {},
        workflow=payload.get("workflow") if isinstance(payload.get("workflow"), dict) else None,
        traceback=payload.get("traceback"),
    )


@router.post("/templates/{template_id}/generate", response_model=PromptGenerationSessionRecord)
def generate_prompt_template_variant(request: Request, template_id: str, payload: PromptTemplateGenerateRequest):
    repository = repo(request)
    template = None
    workflow_result = None
    slot_values = None
    try:
        template = repository.get_prompt_template_by_id(template_id)
        if template.status != "ready":
            raise HTTPException(status_code=409, detail="The prompt template must be re-initialized before generating variants.")
        if template.review_status != "approved":
            raise HTTPException(status_code=409, detail="The prompt template is not approved for application use yet.")
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
        _handle_workflow_error(
            request,
            exc,
            operation="template_generate",
            context={
                "template_id": template_id,
                "theme_keyword": payload.theme_keyword,
                "template": template.model_dump() if template else None,
                "workflow_result": workflow_result,
                "slot_values": slot_values,
            },
        )


@router.post("/generation-sessions/{session_id}/reroll", response_model=PromptGenerationSessionRecord)
def reroll_prompt_template_variant(request: Request, session_id: str, payload: PromptTemplateRerollRequest):
    repository = repo(request)
    session = None
    template = None
    workflow_result = None
    slot_values = None
    previous_variants = None
    try:
        session = repository.get_prompt_generation_session(session_id)
        template = repository.get_prompt_template_by_id(session.template_id)
        if template.status != "ready":
            raise HTTPException(status_code=409, detail="The prompt template must be re-initialized before generating variants.")
        if template.review_status != "approved":
            raise HTTPException(status_code=409, detail="The prompt template is not approved for application use yet.")
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
        _handle_workflow_error(
            request,
            exc,
            operation="template_reroll",
            context={
                "session_id": session_id,
                "rejected_variant_ids": payload.rejected_variant_ids,
                "session": session.model_dump() if session else None,
                "template": template.model_dump() if template else None,
                "previous_variants": [variant.model_dump() for variant in previous_variants] if previous_variants is not None else None,
                "workflow_result": workflow_result,
                "slot_values": slot_values,
            },
        )


@router.post("/prompt-variants/{variant_id}/accept", response_model=PromptGenerationSessionRecord)
def accept_prompt_template_variant(request: Request, variant_id: str):
    try:
        return repo(request).accept_prompt_generation_variant(variant_id)
    except KeyError as exc:
        _not_found(exc)

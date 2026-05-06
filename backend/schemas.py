from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict

class PromptIn(BaseModel):
    language: str = "original"
    text: str
    is_primary: bool = False

class PromptRecord(PromptIn):
    id: str
    item_id: str
    created_at: str
    updated_at: str

class PromptTemplateSlot(BaseModel):
    id: str
    group: str = "content"
    label: str
    original_text: str
    role: Optional[str] = None
    instruction: Optional[str] = None

class PromptTemplateRecord(BaseModel):
    id: str
    item_id: str
    source_language: str
    raw_text_snapshot: str
    marked_text: str
    slots: List[PromptTemplateSlot] = Field(default_factory=list)
    status: str = "ready"
    review_status: str = "pending_review"
    review_notes: Optional[str] = None
    reviewed_at: Optional[str] = None
    analysis_confidence: Optional[float] = None
    analysis_notes: Optional[str] = None
    prompt_source_extracted: bool = False
    prompt_source_strategy: Optional[str] = None
    prompt_source_original_length: Optional[int] = None
    prompt_source_prepared_length: Optional[int] = None
    created_at: str
    updated_at: str

class PromptVariantValue(BaseModel):
    slot_id: str
    text: str

class PromptRenderSegment(BaseModel):
    type: str
    text: str
    changed: bool = False
    slot_id: Optional[str] = None
    label: Optional[str] = None
    group: Optional[str] = None
    before: Optional[str] = None

class PromptGenerationVariantRecord(BaseModel):
    id: str
    session_id: str
    iteration: int
    rendered_text: str
    slot_values: List[PromptVariantValue] = Field(default_factory=list)
    segments: List[PromptRenderSegment] = Field(default_factory=list)
    change_summary: Optional[str] = None
    accepted: bool = False
    created_at: str

class PromptGenerationSessionRecord(BaseModel):
    id: str
    template_id: str
    item_id: str
    theme_keyword: str
    accepted_variant_id: Optional[str] = None
    created_at: str
    updated_at: str
    variants: List[PromptGenerationVariantRecord] = Field(default_factory=list)

class PromptTemplateBundle(BaseModel):
    template: Optional[PromptTemplateRecord] = None
    sessions: List[PromptGenerationSessionRecord] = Field(default_factory=list)

class PromptTemplateOpsItem(BaseModel):
    item_id: str
    title: str
    model: str
    status: str
    review_status: str = "pending_review"
    can_initialize: bool = False
    can_review: bool = False
    published: bool = False
    prompt_language: Optional[str] = None
    prompt_updated_at: Optional[str] = None
    prompt_excerpt: Optional[str] = None
    template_id: Optional[str] = None
    template_status: Optional[str] = None
    template_updated_at: Optional[str] = None
    slot_count: int = 0
    analysis_confidence: Optional[float] = None

class PromptTemplateOpsItemList(BaseModel):
    items: List[PromptTemplateOpsItem] = Field(default_factory=list)
    total: int
    limit: int
    status_counts: dict[str, int] = Field(default_factory=dict)

class PromptTemplateBatchInitRequest(BaseModel):
    item_ids: List[str] = Field(default_factory=list)
    statuses: List[str] = Field(default_factory=lambda: ["missing", "stale"])
    limit: int = Field(default=24, ge=1, le=200)
    force: bool = False
    language: Optional[str] = None

class PromptTemplateBatchInitResult(BaseModel):
    item_id: str
    title: str
    result: str
    detail: Optional[str] = None
    failure_id: Optional[str] = None
    template_id: Optional[str] = None
    template_status: Optional[str] = None
    slot_count: int = 0

class PromptTemplateBatchInitResponse(BaseModel):
    total_candidates: int
    processed: int
    initialized: int = 0
    skipped: int = 0
    failed: int = 0
    results: List[PromptTemplateBatchInitResult] = Field(default_factory=list)

class PromptWorkflowFailureSummary(BaseModel):
    id: str
    created_at: str
    operation: str
    error_class: str
    error_message: str
    item_id: Optional[str] = None
    template_id: Optional[str] = None
    session_id: Optional[str] = None
    theme_keyword: Optional[str] = None
    requested_language: Optional[str] = None
    response_status: Optional[int] = None

class PromptWorkflowFailureRecord(PromptWorkflowFailureSummary):
    context: dict[str, Any] = Field(default_factory=dict)
    workflow: Optional[dict[str, Any]] = None
    traceback: Optional[str] = None

class PromptWorkflowFailureList(BaseModel):
    failures: List[PromptWorkflowFailureSummary] = Field(default_factory=list)
    total: int
    limit: int

class PromptTemplateReviewRequest(BaseModel):
    review_notes: Optional[str] = None

class AdminLoginRequest(BaseModel):
    password: str

class AdminSessionRecord(BaseModel):
    authenticated: bool = False

class ImageRecord(BaseModel):
    id: str
    item_id: str
    original_path: str
    thumb_path: Optional[str] = None
    preview_path: Optional[str] = None
    remote_url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_sha256: Optional[str] = None
    role: str = "result_image"
    sort_order: int = 0
    created_at: str

class ClusterRecord(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    sort_order: int = 0
    count: int = 0
    preview_images: List[str] = Field(default_factory=list)

class TagRecord(BaseModel):
    id: str
    name: str
    kind: str = "general"
    count: int = 0

class ItemCreate(BaseModel):
    title: str
    slug: Optional[str] = None
    model: str = "ChatGPT Image2"
    media_type: str = "image"
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    author: Optional[str] = None
    cluster_id: Optional[str] = None
    cluster_name: Optional[str] = None
    rating: int = 0
    favorite: bool = False
    archived: bool = False
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    prompts: List[PromptIn] = Field(default_factory=list)

class ItemUpdate(BaseModel):
    title: Optional[str] = None
    model: Optional[str] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    author: Optional[str] = None
    cluster_id: Optional[str] = None
    cluster_name: Optional[str] = None
    rating: Optional[int] = None
    favorite: Optional[bool] = None
    archived: Optional[bool] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    prompts: Optional[List[PromptIn]] = None

class ItemSummary(BaseModel):
    id: str
    title: str
    slug: str
    model: str
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    cluster: Optional[ClusterRecord] = None
    tags: List[TagRecord] = Field(default_factory=list)
    prompts: List[PromptRecord] = Field(default_factory=list)
    prompt_snippet: Optional[str] = None
    first_image: Optional[ImageRecord] = None
    rating: int = 0
    favorite: bool = False
    archived: bool = False
    updated_at: str
    created_at: str

class ItemDetail(ItemSummary):
    images: List[ImageRecord] = Field(default_factory=list)
    notes: Optional[str] = None
    author: Optional[str] = None

class PromptImageGenerationResponse(BaseModel):
    status: str = "completed"
    prompt: str
    job_id: Optional[str] = None
    images: List[ImageRecord] = Field(default_factory=list)
    item: ItemDetail

class ItemList(BaseModel):
    items: List[ItemSummary]
    total: int
    limit: int
    offset: int

class PromptTemplateInitRequest(BaseModel):
    language: Optional[str] = None

class PromptTemplateGenerateRequest(BaseModel):
    theme_keyword: str
    rejected_variant_ids: List[str] = Field(default_factory=list)

class PromptTemplateRerollRequest(BaseModel):
    rejected_variant_ids: List[str] = Field(default_factory=list)

class PromptImageGenerateOptions(BaseModel):
    resolution: Optional[Literal["1024x1024", "1536x1024", "1024x1536", "2048x2048", "4096x4096"]] = None
    aspect_ratio: Optional[Literal["auto", "1:1", "4:3", "3:2", "16:9", "9:16"]] = None
    image_count: Optional[int] = Field(default=None, ge=1, le=4)
    style: Optional[Literal["auto", "cinematic", "editorial", "illustration", "photoreal", "fantasy art", "ink & wash"]] = None
    strength: Optional[float] = Field(default=None, ge=0, le=1)

class PromptImageReferenceInput(BaseModel):
    type: Optional[Literal["file-base64", "url"]] = "file-base64"
    label: Optional[str] = None
    role: Optional[str] = None
    note: Optional[str] = None
    mime_type: Optional[str] = None
    image_base64: Optional[str] = None
    image_url: Optional[str] = None

class PromptImageGenerateRequest(BaseModel):
    prompt: str
    generation: Optional[PromptImageGenerateOptions] = None
    references: List[PromptImageReferenceInput] = Field(default_factory=list, max_length=16)

class ImportResult(BaseModel):
    id: str
    item_count: int
    image_count: int
    status: str
    log: str = ""

class CaseIntakeFetchRequest(BaseModel):
    url: str

class CangheGallerySyncRequest(BaseModel):
    dry_run: bool = False
    max_imports: Optional[int] = Field(default=50, ge=1, le=300)
    initialize_templates: bool = True
    approve_templates: bool = False
    admin_password: Optional[str] = None

class CangheGalleryImportedItem(BaseModel):
    item_id: Optional[str] = None
    case_id: str
    title: str
    source_url: Optional[str] = None
    image_url: Optional[str] = None
    template_id: Optional[str] = None

class CangheGallerySyncFailure(BaseModel):
    case_id: str
    title: str
    stage: str
    detail: str

class CangheGallerySyncResponse(BaseModel):
    source_url: str
    source_total: int
    duplicate_count: int = 0
    candidate_count: int = 0
    imported_count: int = 0
    image_count: int = 0
    archived_duplicate_count: int = 0
    template_initialized_count: int = 0
    template_approved_count: int = 0
    dry_run: bool = False
    max_imports: Optional[int] = None
    imported_items: List[CangheGalleryImportedItem] = Field(default_factory=list)
    failures: List[CangheGallerySyncFailure] = Field(default_factory=list)

class CaseIntakeImageCandidate(BaseModel):
    url: str
    source: str
    alt: Optional[str] = None

class CaseIntakeFetchResult(BaseModel):
    url: str
    final_url: str
    title: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    image_url: Optional[str] = None
    image_candidates: List[CaseIntakeImageCandidate] = Field(default_factory=list)
    intake_text: str

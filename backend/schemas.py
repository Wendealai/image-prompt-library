from typing import List, Literal, Optional
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
    analysis_confidence: Optional[float] = None
    analysis_notes: Optional[str] = None
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

class PromptTemplateBulkInitRequest(BaseModel):
    mode: Literal["missing", "stale", "all"] = "missing"
    language: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=500)
    dry_run: bool = False

class PromptTemplateBulkInitItemResult(BaseModel):
    item_id: str
    title: str
    status: str
    template_id: Optional[str] = None
    slot_count: int = 0
    detail: Optional[str] = None

class PromptTemplateBulkInitResult(BaseModel):
    mode: str
    dry_run: bool
    total_candidates: int
    processed_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    results: List[PromptTemplateBulkInitItemResult] = Field(default_factory=list)

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

class ImportResult(BaseModel):
    id: str
    item_count: int
    image_count: int
    status: str
    log: str = ""

class CaseIntakeFetchRequest(BaseModel):
    url: str

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

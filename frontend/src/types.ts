export type ViewMode = 'explore' | 'cards';
export type UploadImageRole = 'result_image' | 'reference_image';
export interface PromptRecord { id: string; item_id: string; language: string; text: string; is_primary: boolean }
export interface PromptTemplateSlot { id: string; group: string; label: string; original_text: string; role?: string; instruction?: string }
export interface PromptVariantValue { slot_id: string; text: string }
export interface PromptRenderSegment { type: string; text: string; changed: boolean; slot_id?: string; label?: string; group?: string; before?: string }
export interface PromptGenerationVariantRecord { id: string; session_id: string; iteration: number; rendered_text: string; slot_values: PromptVariantValue[]; segments: PromptRenderSegment[]; change_summary?: string; accepted: boolean; created_at: string }
export interface PromptGenerationSessionRecord { id: string; template_id: string; item_id: string; theme_keyword: string; accepted_variant_id?: string; created_at: string; updated_at: string; variants: PromptGenerationVariantRecord[] }
export interface PromptTemplateRecord { id: string; item_id: string; source_language: string; raw_text_snapshot: string; marked_text: string; slots: PromptTemplateSlot[]; status: string; review_status: string; review_notes?: string; reviewed_at?: string; analysis_confidence?: number; analysis_notes?: string; created_at: string; updated_at: string }
export interface PromptTemplateBundle { template?: PromptTemplateRecord; sessions: PromptGenerationSessionRecord[] }
export interface PromptImageGenerationOptions { resolution?: string; aspect_ratio?: string; image_count?: number; style?: string }
export interface PromptImageGenerationResponse { status: string; prompt: string; job_id?: string; images: ImageRecord[]; item: ItemDetail }
export interface PromptTemplateOpsItem { item_id: string; title: string; model: string; status: string; review_status: string; can_initialize: boolean; can_review: boolean; published: boolean; prompt_language?: string; prompt_updated_at?: string; prompt_excerpt?: string; template_id?: string; template_status?: string; template_updated_at?: string; slot_count: number; analysis_confidence?: number }
export interface PromptTemplateOpsItemList { items: PromptTemplateOpsItem[]; total: number; limit: number; status_counts: Record<string, number> }
export interface PromptTemplateBatchInitRequest { item_ids?: string[]; statuses?: string[]; limit?: number; force?: boolean; language?: string }
export interface PromptTemplateBatchInitResult { item_id: string; title: string; result: string; detail?: string; failure_id?: string; template_id?: string; template_status?: string; slot_count: number }
export interface PromptTemplateBatchInitResponse { total_candidates: number; processed: number; initialized: number; skipped: number; failed: number; results: PromptTemplateBatchInitResult[] }
export interface PromptTemplateReviewRequest { review_notes?: string }
export interface AdminLoginRequest { password: string }
export interface AdminSessionRecord { authenticated: boolean }
export interface PromptWorkflowFailureSummary { id: string; created_at: string; operation: string; error_class: string; error_message: string; item_id?: string; template_id?: string; session_id?: string; theme_keyword?: string; requested_language?: string; response_status?: number }
export interface PromptWorkflowFailureRecord extends PromptWorkflowFailureSummary { context: Record<string, unknown>; workflow?: Record<string, unknown>; traceback?: string }
export interface PromptWorkflowFailureList { failures: PromptWorkflowFailureSummary[]; total: number; limit: number }
export interface ImageRecord { id: string; item_id: string; original_path: string; thumb_path?: string; preview_path?: string; width?: number; height?: number; role?: UploadImageRole }
export interface ClusterRecord { id: string; name: string; description?: string; count: number; preview_images: string[] }
export interface TagRecord { id: string; name: string; kind: string; count: number }
export interface AppConfig { version: string; library_path: string; database_path: string; preferred_prompt_language?: string }
export interface ItemSummary { id: string; title: string; slug: string; model: string; source_name?: string; source_url?: string; cluster?: ClusterRecord; tags: TagRecord[]; prompts: PromptRecord[]; prompt_snippet?: string; first_image?: ImageRecord; rating: number; favorite: boolean; archived: boolean; updated_at: string; created_at: string }
export interface ItemDetail extends ItemSummary { images: ImageRecord[]; notes?: string; author?: string }
export interface ItemList { items: ItemSummary[]; total: number; limit: number; offset: number }
export interface ItemCreate { title: string; cluster_name?: string; tags?: string[]; prompts: Array<{language: string; text: string; is_primary?: boolean}>; model?: string; source_name?: string; source_url?: string; author?: string; notes?: string }
export interface CaseIntakeImageCandidate { url: string; source: string; alt?: string }
export interface CaseIntakeFetchResult { url: string; final_url: string; title?: string; description?: string; author?: string; image_url?: string; image_candidates?: CaseIntakeImageCandidate[]; intake_text: string }

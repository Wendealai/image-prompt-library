export type ViewMode = 'explore' | 'cards';
export type UploadImageRole = 'result_image' | 'reference_image';
export interface PromptRecord { id: string; item_id: string; language: string; text: string; is_primary: boolean }
export interface PromptTemplateSlot { id: string; group: string; label: string; original_text: string; role?: string; instruction?: string }
export interface PromptVariantValue { slot_id: string; text: string }
export interface PromptRenderSegment { type: string; text: string; changed: boolean; slot_id?: string; label?: string; group?: string; before?: string }
export interface PromptGenerationVariantRecord { id: string; session_id: string; iteration: number; rendered_text: string; slot_values: PromptVariantValue[]; segments: PromptRenderSegment[]; change_summary?: string; accepted: boolean; created_at: string }
export interface PromptGenerationSessionRecord { id: string; template_id: string; item_id: string; theme_keyword: string; accepted_variant_id?: string; created_at: string; updated_at: string; variants: PromptGenerationVariantRecord[] }
export interface PromptTemplateRecord { id: string; item_id: string; source_language: string; raw_text_snapshot: string; marked_text: string; slots: PromptTemplateSlot[]; status: string; analysis_confidence?: number; analysis_notes?: string; created_at: string; updated_at: string }
export interface PromptTemplateBundle { template?: PromptTemplateRecord; sessions: PromptGenerationSessionRecord[] }
export type PromptTemplateBulkInitMode = 'missing' | 'stale' | 'all';
export interface PromptTemplateBulkInitRequest { mode?: PromptTemplateBulkInitMode; language?: string; limit?: number; dry_run?: boolean }
export interface PromptTemplateBulkInitItemResult { item_id: string; title: string; status: string; template_id?: string; slot_count: number; detail?: string }
export interface PromptTemplateBulkInitResult { mode: PromptTemplateBulkInitMode; dry_run: boolean; total_candidates: number; processed_count: number; skipped_count: number; failed_count: number; results: PromptTemplateBulkInitItemResult[] }
export interface ImageRecord { id: string; item_id: string; original_path: string; thumb_path?: string; preview_path?: string; remote_url?: string; width?: number; height?: number; role?: UploadImageRole }
export interface NanobananaGeneration { resolution?: string; aspectRatio?: string; imageCount?: number; quality?: 'low' | 'medium' | 'high'; outputFormat?: 'png' | 'jpeg' | 'webp'; strength?: number }
export interface NanobananaSourceItem { label?: string; role?: string; note?: string; imageUrl: string; mimeType?: string }
export interface NanobananaItemImageGenerationRequest { promptText?: string; promptLanguage?: string; stylePack?: string; generation?: NanobananaGeneration; sourceItems?: NanobananaSourceItem[]; idempotencyKey?: string; wait?: boolean; timeoutMs?: number; pollIntervalMs?: number }
export interface NanobananaItemImageGenerationResult { create: Record<string, unknown>; terminal?: Record<string, unknown> | null; mapped: Record<string, { url?: string; key?: string; [key: string]: unknown }>; stored_images: ImageRecord[] }
export interface ClusterRecord { id: string; name: string; description?: string; count: number; preview_images: string[] }
export interface TagRecord { id: string; name: string; kind: string; count: number }
export interface AppConfig { version: string; library_path: string; database_path: string; preferred_prompt_language?: string }
export interface ItemSummary { id: string; title: string; slug: string; model: string; source_name?: string; source_url?: string; cluster?: ClusterRecord; tags: TagRecord[]; prompts: PromptRecord[]; prompt_snippet?: string; first_image?: ImageRecord; rating: number; favorite: boolean; archived: boolean; updated_at: string; created_at: string }
export interface ItemDetail extends ItemSummary { images: ImageRecord[]; notes?: string; author?: string }
export interface ItemList { items: ItemSummary[]; total: number; limit: number; offset: number }
export interface ItemCreate { title: string; cluster_name?: string; tags?: string[]; prompts: Array<{language: string; text: string; is_primary?: boolean}>; model?: string; source_name?: string; source_url?: string; author?: string; notes?: string }
export interface CaseIntakeImageCandidate { url: string; source: string; alt?: string }
export interface CaseIntakeFetchResult { url: string; final_url: string; title?: string; description?: string; author?: string; image_url?: string; image_candidates?: CaseIntakeImageCandidate[]; intake_text: string }

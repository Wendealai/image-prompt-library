import type { AdminSessionRecord, AppConfig, CaseIntakeFetchResult, ClusterRecord, ItemCreate, ItemDetail, ItemList, NanobananaItemImageGenerationRequest, NanobananaItemImageGenerationResult, PromptGenerationSessionRecord, PromptImageGenerationOptions, PromptImageGenerationResponse, PromptImageReferenceInput, PromptTemplateBatchInitRequest, PromptTemplateBatchInitResponse, PromptTemplateBulkInitRequest, PromptTemplateBulkInitResult, PromptTemplateBundle, PromptTemplateOpsItemList, PromptTemplateRecord, PromptTemplateReviewRequest, PromptWorkflowFailureList, PromptWorkflowFailureRecord, TagRecord, UploadImageRole } from '../types';
import { fileFromUrl, json } from './http';

export const caseIntakeImageUrl = (url: string) => `/api/intake/image?url=${encodeURIComponent(url)}`;

function itemListParams(params: Record<string, string | number | boolean | undefined>) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') qs.set(key, String(value));
  });
  return qs;
}

function uploadImage(itemId: string, file: File, role: UploadImageRole = 'result_image') {
  const formData = new FormData();
  formData.set('file', file);
  formData.set('role', role);
  return json(`/api/items/${itemId}/images`, { method: 'POST', body: formData });
}

function promptTemplateOpsParams(params: { status?: string[]; limit?: number } = {}) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set('limit', String(params.limit));
  params.status?.forEach(value => qs.append('status', value));
  return qs;
}

export const localApi = {
  health: () => json<{ok: boolean; version: string}>('/api/health'),
  config: () => json<AppConfig>('/api/config'),
  items: (params: Record<string, string | number | boolean | undefined>) => json<ItemList>(`/api/items?${itemListParams(params)}`),
  item: (id: string) => json<ItemDetail>(`/api/items/${id}`),
  createItem: (payload: ItemCreate) => json<ItemDetail>('/api/items', { method: 'POST', body: JSON.stringify(payload) }),
  updateItem: (id: string, payload: Partial<ItemCreate>) => json<ItemDetail>(`/api/items/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteItem: (id: string) => json<ItemDetail>(`/api/items/${id}`, { method: 'DELETE' }),
  favorite: (id: string) => json<ItemDetail>(`/api/items/${id}/favorite`, { method: 'POST' }),
  uploadImage,
  deleteImage: (itemId: string, imageId: string) => json<ItemDetail>(`/api/items/${itemId}/images/${imageId}`, { method: 'DELETE' }),
  fetchCaseIntake: (url: string) => json<CaseIntakeFetchResult>('/api/intake/fetch', { method: 'POST', body: JSON.stringify({ url }) }),
  fetchCaseIntakeImage: (url: string) => fileFromUrl(caseIntakeImageUrl(url)),
  promptTemplate: (itemId: string) => json<PromptTemplateBundle>(`/api/items/${itemId}/prompt-template`),
  bulkInitPromptTemplates: (payload: PromptTemplateBulkInitRequest) => json<PromptTemplateBulkInitResult>(`/api/prompt-templates/bulk-init`, { method: 'POST', body: JSON.stringify(payload) }),
  adminPromptTemplate: (itemId: string) => json<PromptTemplateBundle>(`/api/admin/items/${itemId}/prompt-template`),
  adminSession: () => json<AdminSessionRecord>('/api/admin/auth/session'),
  adminLogin: (password: string) => json<AdminSessionRecord>('/api/admin/auth/login', { method: 'POST', body: JSON.stringify({ password }) }),
  adminLogout: () => json<AdminSessionRecord>('/api/admin/auth/logout', { method: 'POST' }),
  adminInitPromptTemplate: (itemId: string, language?: string) => json<PromptTemplateBundle>(`/api/admin/items/${itemId}/prompt-template/init`, { method: 'POST', body: JSON.stringify(language ? { language } : {}) }),
  generatePromptVariant: (templateId: string, themeKeyword: string, rejectedVariantIds: string[] = []) => json<PromptGenerationSessionRecord>(`/api/templates/${templateId}/generate`, { method: 'POST', body: JSON.stringify({ theme_keyword: themeKeyword, rejected_variant_ids: rejectedVariantIds }) }),
  rerollPromptVariant: (sessionId: string, rejectedVariantIds: string[] = []) => json<PromptGenerationSessionRecord>(`/api/generation-sessions/${sessionId}/reroll`, { method: 'POST', body: JSON.stringify({ rejected_variant_ids: rejectedVariantIds }) }),
  acceptPromptVariant: (variantId: string) => json<PromptGenerationSessionRecord>(`/api/prompt-variants/${variantId}/accept`, { method: 'POST' }),
  generateImageFromPrompt: (itemId: string, prompt: string, generation?: PromptImageGenerationOptions, references: PromptImageReferenceInput[] = []) => json<PromptImageGenerationResponse>(`/api/items/${itemId}/generate-image`, { method: 'POST', body: JSON.stringify({ prompt, ...(generation ? { generation } : {}), ...(references.length > 0 ? { references } : {}) }) }),
  generateItemImage: (itemId: string, payload: NanobananaItemImageGenerationRequest = {}) => json<NanobananaItemImageGenerationResult>(`/api/items/${itemId}/nanobanana/images`, { method: 'POST', body: JSON.stringify(payload) }),
  adminPromptTemplateOpsItems: (params: { status?: string[]; limit?: number } = {}) => json<PromptTemplateOpsItemList>(`/api/admin/prompt-templates/ops/items?${promptTemplateOpsParams(params).toString()}`),
  adminBatchInitPromptTemplates: (payload: PromptTemplateBatchInitRequest) => json<PromptTemplateBatchInitResponse>('/api/admin/prompt-templates/ops/batch-init', { method: 'POST', body: JSON.stringify(payload) }),
  adminPromptTemplateFailures: (limit = 50) => json<PromptWorkflowFailureList>(`/api/admin/prompt-template-failures?limit=${limit}`),
  adminPromptTemplateFailure: (failureId: string) => json<PromptWorkflowFailureRecord>(`/api/admin/prompt-template-failures/${failureId}`),
  adminApprovePromptTemplate: (templateId: string, payload: PromptTemplateReviewRequest = {}) => json<PromptTemplateRecord>(`/api/admin/prompt-templates/${templateId}/approve`, { method: 'POST', body: JSON.stringify(payload) }),
  adminRejectPromptTemplate: (templateId: string, payload: PromptTemplateReviewRequest = {}) => json<PromptTemplateRecord>(`/api/admin/prompt-templates/${templateId}/reject`, { method: 'POST', body: JSON.stringify(payload) }),
  clusters: () => json<ClusterRecord[]>('/api/clusters'),
  tags: () => json<TagRecord[]>('/api/tags'),
};

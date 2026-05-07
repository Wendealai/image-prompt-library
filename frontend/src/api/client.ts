import type { AdminSessionRecord, AppConfig, CaseIntakeFetchResult, ClusterRecord, ItemCreate, ItemDetail, ItemList, ItemSummary, PromptGenerationSessionRecord, PromptImageGenerationOptions, PromptImageGenerationResponse, PromptImageReferenceInput, PromptTemplateBatchInitRequest, PromptTemplateBatchInitResponse, PromptTemplateBundle, PromptTemplateOpsItemList, PromptTemplateRecord, PromptTemplateReviewRequest, PromptWorkflowFailureList, PromptWorkflowFailureRecord, TagRecord, UploadImageRole } from '../types';

const API = '';
const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true';
const DEMO_DATA_BASE = `${import.meta.env.BASE_URL || '/'}demo-data`.replace(/\/+/g, '/');

function demoUrl(path: string) {
  const base = import.meta.env.BASE_URL || '/';
  return `${base}${path.replace(/^\/+/, '')}`;
}

function summarizeResponseError(body: string, status: number) {
  const trimmed = body.trim();
  if (!trimmed) return `Request failed with status ${status}.`;
  try {
    const parsed = JSON.parse(trimmed) as { detail?: string; message?: string };
    if (typeof parsed.detail === 'string' && parsed.detail.trim()) return parsed.detail.trim();
    if (typeof parsed.message === 'string' && parsed.message.trim()) return parsed.message.trim();
  } catch {
    // Fall back to the raw response body below.
  }
  if (/^<!doctype html/i.test(trimmed) || /^<html/i.test(trimmed)) return `Request failed with status ${status}.`;
  return trimmed;
}

export class ApiError extends Error {
  status: number;
  body: string;

  constructor(status: number, body: string) {
    super(summarizeResponseError(body, status));
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API + url, { credentials: 'same-origin', headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' }, ...init });
  if (!r.ok) throw new ApiError(r.status, await r.text());
  return r.json();
}

async function demoJson<T>(path: string): Promise<T> {
  const r = await fetch(demoUrl(path));
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function fileFromUrl(url: string, init?: RequestInit): Promise<File> {
  const r = await fetch(API + url, init);
  if (!r.ok) throw new Error(await r.text());
  const blob = await r.blob();
  const filename = r.headers.get('x-intake-filename') || 'reference-image';
  return new File([blob], filename, { type: blob.type || 'image/png' });
}

let demoItemsCache: Promise<ItemSummary[]> | undefined;
const demoItems = () => demoItemsCache ||= demoJson<ItemSummary[]>('demo-data/items.json');

function normalizeSearchText(item: ItemSummary) {
  return [
    item.title,
    item.cluster?.name,
    item.source_name,
    item.model,
    ...item.tags.map(tag => tag.name),
    ...item.prompts.map(prompt => prompt.text),
  ].filter(Boolean).join('\n').toLowerCase();
}

async function demoItemList(params: Record<string, string | number | boolean | undefined>): Promise<ItemList> {
  const allItems = await demoItems();
  const q = String(params.q || '').trim().toLowerCase();
  const cluster = String(params.cluster || '').trim();
  const tag = String(params.tag || '').trim();
  const limit = Math.max(0, Number(params.limit || 100));
  const offset = Math.max(0, Number(params.offset || 0));
  const filtered = allItems.filter(item => {
    if (cluster && item.cluster?.id !== cluster) return false;
    if (tag && !item.tags.some(itemTag => itemTag.name === tag || itemTag.id === tag)) return false;
    if (q && !normalizeSearchText(item).includes(q)) return false;
    return true;
  });
  return { items: filtered.slice(offset, offset + limit), total: filtered.length, limit, offset };
}

async function demoItem(id: string): Promise<ItemDetail> {
  const allItems = await demoItems();
  const item = allItems.find(candidate => candidate.id === id);
  if (!item) throw new Error('Demo item not found');
  return { ...item, images: item.first_image ? [item.first_image] : [], notes: 'Online sandbox sample. Images are compressed for the web demo; run the app locally for your own private full library.', author: (item as ItemDetail).author };
}

function demoReadOnly(): Promise<never> {
  return Promise.reject(new Error('The online sandbox is read-only. Run Image Prompt Library locally to create your own private library.'));
}

function demoAiUnavailable(): Promise<never> {
  return Promise.reject(new Error('AI prompt rewriting is unavailable in the online sandbox. Run Image Prompt Library locally with your own backend and n8n workflow.'));
}

export const mediaUrl = (path?: string) => {
  if (!path) return '';
  if (isDemoMode && path.startsWith('demo-data/')) return demoUrl(path);
  return `/media/${path}`;
};

export const caseIntakeImageUrl = (url: string) => `/api/intake/image?url=${encodeURIComponent(url)}`;

export const api = isDemoMode ? {
  health: () => Promise.resolve({ ok: true, version: 'demo' }),
  config: () => Promise.resolve<AppConfig>({ version: 'demo', library_path: 'GitHub Pages read-only sandbox', database_path: 'Static JSON bundle', preferred_prompt_language: 'en' }),
  items: demoItemList,
  item: demoItem,
  createItem: (_payload: ItemCreate) => demoReadOnly(),
  updateItem: (_id: string, _payload: Partial<ItemCreate>) => demoReadOnly(),
  deleteItem: (_id: string) => demoReadOnly(),
  favorite: (_id: string) => demoReadOnly(),
  uploadImage: (_id: string, _file: File, _role: UploadImageRole = 'result_image') => demoReadOnly(),
  deleteImage: (_itemId: string, _imageId: string) => demoReadOnly(),
  fetchCaseIntake: (_url: string) => Promise.reject(new Error('URL intake is unavailable in the online sandbox. Run the app locally to fetch case pages.')),
  fetchCaseIntakeImage: (_url: string) => Promise.reject(new Error('Remote image intake is unavailable in the online sandbox. Run the app locally to fetch case pages.')),
  promptTemplate: (_itemId: string) => demoAiUnavailable(),
  adminSession: () => Promise.resolve<AdminSessionRecord>({ authenticated: false }),
  adminLogin: (_password: string) => Promise.reject(new Error('Admin is unavailable in the online sandbox. Run Image Prompt Library locally with your own backend.')),
  adminLogout: () => Promise.resolve<AdminSessionRecord>({ authenticated: false }),
  adminPromptTemplate: (_itemId: string) => demoAiUnavailable(),
  adminInitPromptTemplate: (_itemId: string, _language?: string) => demoAiUnavailable(),
  generatePromptVariant: (_templateId: string, _themeKeyword: string, _rejectedVariantIds: string[] = []) => demoAiUnavailable(),
  rerollPromptVariant: (_sessionId: string, _rejectedVariantIds: string[] = []) => demoAiUnavailable(),
  acceptPromptVariant: (_variantId: string) => demoAiUnavailable(),
  generateImageFromPrompt: (_itemId: string, _prompt: string, _generation?: PromptImageGenerationOptions, _references?: PromptImageReferenceInput[]) => demoAiUnavailable(),
  adminPromptTemplateOpsItems: (_params?: { status?: string[]; limit?: number }) => demoAiUnavailable(),
  adminBatchInitPromptTemplates: (_payload: PromptTemplateBatchInitRequest) => demoAiUnavailable(),
  adminPromptTemplateFailures: (_limit = 50) => demoAiUnavailable(),
  adminPromptTemplateFailure: (_failureId: string) => demoAiUnavailable(),
  adminApprovePromptTemplate: (_templateId: string, _payload: PromptTemplateReviewRequest = {}) => demoAiUnavailable(),
  adminRejectPromptTemplate: (_templateId: string, _payload: PromptTemplateReviewRequest = {}) => demoAiUnavailable(),
  clusters: () => demoJson<ClusterRecord[]>('demo-data/clusters.json'),
  tags: () => demoJson<TagRecord[]>('demo-data/tags.json'),
} : {
  health: () => json<{ok: boolean; version: string}>('/api/health'),
  config: () => json<AppConfig>('/api/config'),
  items: (params: Record<string, string | number | boolean | undefined>) => { const qs = new URLSearchParams(); Object.entries(params).forEach(([k,v]) => { if (v !== undefined && v !== '') qs.set(k, String(v)); }); return json<ItemList>(`/api/items?${qs}`); },
  item: (id: string) => json<ItemDetail>(`/api/items/${id}`),
  createItem: (payload: ItemCreate) => json<ItemDetail>('/api/items', { method: 'POST', body: JSON.stringify(payload) }),
  updateItem: (id: string, payload: Partial<ItemCreate>) => json<ItemDetail>(`/api/items/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteItem: (id: string) => json<ItemDetail>(`/api/items/${id}`, { method: 'DELETE' }),
  favorite: (id: string) => json<ItemDetail>(`/api/items/${id}/favorite`, { method: 'POST' }),
  uploadImage: (id: string, file: File, role: UploadImageRole = 'result_image') => { const fd = new FormData(); fd.set('file', file); fd.set('role', role); return json(`/api/items/${id}/images`, { method: 'POST', body: fd }); },
  deleteImage: (itemId: string, imageId: string) => json<ItemDetail>(`/api/items/${itemId}/images/${imageId}`, { method: 'DELETE' }),
  fetchCaseIntake: (url: string) => json<CaseIntakeFetchResult>('/api/intake/fetch', { method: 'POST', body: JSON.stringify({ url }) }),
  fetchCaseIntakeImage: (url: string) => fileFromUrl(caseIntakeImageUrl(url)),
  promptTemplate: (itemId: string) => json<PromptTemplateBundle>(`/api/items/${itemId}/prompt-template`),
  adminPromptTemplate: (itemId: string) => json<PromptTemplateBundle>(`/api/admin/items/${itemId}/prompt-template`),
  adminSession: () => json<AdminSessionRecord>('/api/admin/auth/session'),
  adminLogin: (password: string) => json<AdminSessionRecord>('/api/admin/auth/login', { method: 'POST', body: JSON.stringify({ password }) }),
  adminLogout: () => json<AdminSessionRecord>('/api/admin/auth/logout', { method: 'POST' }),
  adminInitPromptTemplate: (itemId: string, language?: string) => json<PromptTemplateBundle>(`/api/admin/items/${itemId}/prompt-template/init`, { method: 'POST', body: JSON.stringify(language ? { language } : {}) }),
  generatePromptVariant: (templateId: string, themeKeyword: string, rejectedVariantIds: string[] = []) => json<PromptGenerationSessionRecord>(`/api/templates/${templateId}/generate`, { method: 'POST', body: JSON.stringify({ theme_keyword: themeKeyword, rejected_variant_ids: rejectedVariantIds }) }),
  rerollPromptVariant: (sessionId: string, rejectedVariantIds: string[] = []) => json<PromptGenerationSessionRecord>(`/api/generation-sessions/${sessionId}/reroll`, { method: 'POST', body: JSON.stringify({ rejected_variant_ids: rejectedVariantIds }) }),
  acceptPromptVariant: (variantId: string) => json<PromptGenerationSessionRecord>(`/api/prompt-variants/${variantId}/accept`, { method: 'POST' }),
  generateImageFromPrompt: (itemId: string, prompt: string, generation?: PromptImageGenerationOptions, references: PromptImageReferenceInput[] = []) => json<PromptImageGenerationResponse>(`/api/items/${itemId}/generate-image`, { method: 'POST', body: JSON.stringify({ prompt, ...(generation ? { generation } : {}), ...(references.length > 0 ? { references } : {}) }) }),
  adminPromptTemplateOpsItems: (params: { status?: string[]; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.limit) qs.set('limit', String(params.limit));
    params.status?.forEach(value => qs.append('status', value));
    return json<PromptTemplateOpsItemList>(`/api/admin/prompt-templates/ops/items?${qs.toString()}`);
  },
  adminBatchInitPromptTemplates: (payload: PromptTemplateBatchInitRequest) => json<PromptTemplateBatchInitResponse>('/api/admin/prompt-templates/ops/batch-init', { method: 'POST', body: JSON.stringify(payload) }),
  adminPromptTemplateFailures: (limit = 50) => json<PromptWorkflowFailureList>(`/api/admin/prompt-template-failures?limit=${limit}`),
  adminPromptTemplateFailure: (failureId: string) => json<PromptWorkflowFailureRecord>(`/api/admin/prompt-template-failures/${failureId}`),
  adminApprovePromptTemplate: (templateId: string, payload: PromptTemplateReviewRequest = {}) => json<PromptTemplateRecord>(`/api/admin/prompt-templates/${templateId}/approve`, { method: 'POST', body: JSON.stringify(payload) }),
  adminRejectPromptTemplate: (templateId: string, payload: PromptTemplateReviewRequest = {}) => json<PromptTemplateRecord>(`/api/admin/prompt-templates/${templateId}/reject`, { method: 'POST', body: JSON.stringify(payload) }),
  clusters: () => json<ClusterRecord[]>('/api/clusters'),
  tags: () => json<TagRecord[]>('/api/tags'),
};

export { DEMO_DATA_BASE, isDemoMode };

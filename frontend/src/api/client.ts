import type { AppConfig, CaseIntakeFetchResult, ClusterRecord, ItemCreate, ItemDetail, ItemList, ItemSummary, NanobananaItemImageGenerationRequest, NanobananaItemImageGenerationResult, PromptGenerationSessionRecord, PromptTemplateBulkInitRequest, PromptTemplateBulkInitResult, PromptTemplateBundle, TagRecord, UploadImageRole } from '../types';

const API = '';
const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true';
const DEMO_DATA_BASE = `${import.meta.env.BASE_URL || '/'}demo-data`.replace(/\/+/g, '/');
const DEMO_ASSET_VERSION = (import.meta.env.VITE_DEMO_ASSET_VERSION || '').trim();

function demoUrl(path: string) {
  const base = import.meta.env.BASE_URL || '/';
  const url = `${base}${path.replace(/^\/+/, '')}`;
  if (!isDemoMode || !DEMO_ASSET_VERSION) return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}v=${encodeURIComponent(DEMO_ASSET_VERSION)}`;
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API + url, { headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' }, ...init });
  if (!r.ok) throw new Error(await r.text());
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

function demoImageGenerationUnavailable(): Promise<never> {
  return Promise.reject(new Error('Direct image generation is unavailable in the online sandbox. Run Image Prompt Library locally with your Nanobanana image API token.'));
}

export const mediaUrl = (path?: string) => {
  if (!path) return '';
  if (/^https?:\/\//i.test(path)) return path;
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
  fetchCaseIntake: (_url: string) => Promise.reject(new Error('URL intake is unavailable in the online sandbox. Run the app locally to fetch case pages.')),
  fetchCaseIntakeImage: (_url: string) => Promise.reject(new Error('Remote image intake is unavailable in the online sandbox. Run the app locally to fetch case pages.')),
  promptTemplate: (_itemId: string) => demoAiUnavailable(),
  initPromptTemplate: (_itemId: string, _language?: string) => demoAiUnavailable(),
  bulkInitPromptTemplates: (_payload: PromptTemplateBulkInitRequest = {}) => demoAiUnavailable(),
  generatePromptVariant: (_templateId: string, _themeKeyword: string, _rejectedVariantIds: string[] = []) => demoAiUnavailable(),
  rerollPromptVariant: (_sessionId: string, _rejectedVariantIds: string[] = []) => demoAiUnavailable(),
  acceptPromptVariant: (_variantId: string) => demoAiUnavailable(),
  generateItemImage: (_itemId: string, _payload: NanobananaItemImageGenerationRequest = {}) => demoImageGenerationUnavailable(),
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
  fetchCaseIntake: (url: string) => json<CaseIntakeFetchResult>('/api/intake/fetch', { method: 'POST', body: JSON.stringify({ url }) }),
  fetchCaseIntakeImage: (url: string) => fileFromUrl(caseIntakeImageUrl(url)),
  promptTemplate: (itemId: string) => json<PromptTemplateBundle>(`/api/items/${itemId}/prompt-template`),
  initPromptTemplate: (itemId: string, language?: string) => json<PromptTemplateBundle>(`/api/items/${itemId}/prompt-template/init`, { method: 'POST', body: JSON.stringify(language ? { language } : {}) }),
  bulkInitPromptTemplates: (payload: PromptTemplateBulkInitRequest = {}) => json<PromptTemplateBulkInitResult>('/api/prompt-templates/bulk-init', { method: 'POST', body: JSON.stringify(payload) }),
  generatePromptVariant: (templateId: string, themeKeyword: string, rejectedVariantIds: string[] = []) => json<PromptGenerationSessionRecord>(`/api/templates/${templateId}/generate`, { method: 'POST', body: JSON.stringify({ theme_keyword: themeKeyword, rejected_variant_ids: rejectedVariantIds }) }),
  rerollPromptVariant: (sessionId: string, rejectedVariantIds: string[] = []) => json<PromptGenerationSessionRecord>(`/api/generation-sessions/${sessionId}/reroll`, { method: 'POST', body: JSON.stringify({ rejected_variant_ids: rejectedVariantIds }) }),
  acceptPromptVariant: (variantId: string) => json<PromptGenerationSessionRecord>(`/api/prompt-variants/${variantId}/accept`, { method: 'POST' }),
  generateItemImage: (itemId: string, payload: NanobananaItemImageGenerationRequest = {}) => json<NanobananaItemImageGenerationResult>(`/api/items/${itemId}/nanobanana/images`, { method: 'POST', body: JSON.stringify(payload) }),
  clusters: () => json<ClusterRecord[]>('/api/clusters'),
  tags: () => json<TagRecord[]>('/api/tags'),
};

export { DEMO_DATA_BASE, isDemoMode };

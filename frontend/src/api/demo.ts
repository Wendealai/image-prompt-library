import type { AdminSessionRecord, AppConfig, CaseIntakeFetchResult, ClusterRecord, GeneratedImageHistoryList, ItemCreate, ItemDetail, ItemList, ItemSummary, NanobananaItemImageGenerationRequest, PromptImageGenerationOptions, PromptImageGenerationRunRecord, PromptImageReferenceInput, PromptTemplateBulkInitRequest, PromptTemplateReviewRequest, TagRecord, UploadImageRole } from '../types';

export const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true';
export const DEMO_ASSET_VERSION = (import.meta.env.VITE_DEMO_ASSET_VERSION || '').trim();
export const DEMO_DATA_BASE = `${import.meta.env.BASE_URL || '/'}demo-data`.replace(/\/+/g, '/');

export function demoUrl(path: string) {
  const base = import.meta.env.BASE_URL || '/';
  const url = `${base}${path.replace(/^\/+/, '')}`;
  if (!isDemoMode || !DEMO_ASSET_VERSION) return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}v=${encodeURIComponent(DEMO_ASSET_VERSION)}`;
}

async function demoJson<T>(path: string): Promise<T> {
  const r = await fetch(demoUrl(path));
  if (!r.ok) throw new Error(await r.text());
  return r.json();
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

export const demoApi = {
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
  fetchCaseIntake: (_url: string) => Promise.reject(new Error('URL intake is unavailable in the online sandbox. Run the app locally to fetch case pages.')) as Promise<CaseIntakeFetchResult>,
  fetchCaseIntakeImage: (_url: string) => Promise.reject(new Error('Remote image intake is unavailable in the online sandbox. Run the app locally to fetch case pages.')) as Promise<File>,
  promptTemplate: (_itemId: string) => demoAiUnavailable(),
  bulkInitPromptTemplates: (_payload: PromptTemplateBulkInitRequest) => demoAiUnavailable(),
  adminSession: () => Promise.resolve<AdminSessionRecord>({ authenticated: false }),
  adminLogin: (_password: string) => Promise.reject(new Error('Admin is unavailable in the online sandbox. Run Image Prompt Library locally with your own backend.')),
  adminLogout: () => Promise.resolve<AdminSessionRecord>({ authenticated: false }),
  adminPromptTemplate: (_itemId: string) => demoAiUnavailable(),
  adminInitPromptTemplate: (_itemId: string, _language?: string) => demoAiUnavailable(),
  generatePromptVariant: (_templateId: string, _themeKeyword: string, _rejectedVariantIds: string[] = []) => demoAiUnavailable(),
  rerollPromptVariant: (_sessionId: string, _rejectedVariantIds: string[] = []) => demoAiUnavailable(),
  acceptPromptVariant: (_variantId: string) => demoAiUnavailable(),
  generateImageFromPrompt: (_itemId: string, _prompt: string, _generation?: PromptImageGenerationOptions, _references?: PromptImageReferenceInput[]) => demoAiUnavailable(),
  promptImageGenerationRuns: (_itemId: string) => Promise.resolve<PromptImageGenerationRunRecord[]>([]),
  generatedImageHistory: (_params?: { q?: string; cluster?: string; limit?: number; offset?: number }) => Promise.resolve<GeneratedImageHistoryList>({ items: [], total: 0, limit: 0, offset: 0 }),
  generateItemImage: (_itemId: string, _payload: NanobananaItemImageGenerationRequest = {}) => demoImageGenerationUnavailable(),
  itemImageGenerationStatus: (_itemId: string, _batchId: string) => demoImageGenerationUnavailable(),
  adminPromptTemplateOpsItems: (_params?: { status?: string[]; limit?: number }) => demoAiUnavailable(),
  adminBatchInitPromptTemplates: (_payload: unknown) => demoAiUnavailable(),
  adminPromptTemplateFailures: (_limit = 50) => demoAiUnavailable(),
  adminPromptTemplateFailure: (_failureId: string) => demoAiUnavailable(),
  adminApprovePromptTemplate: (_templateId: string, _payload: PromptTemplateReviewRequest = {}) => demoAiUnavailable(),
  adminRejectPromptTemplate: (_templateId: string, _payload: PromptTemplateReviewRequest = {}) => demoAiUnavailable(),
  clusters: () => demoJson<ClusterRecord[]>('demo-data/clusters.json'),
  tags: () => demoJson<TagRecord[]>('demo-data/tags.json'),
};

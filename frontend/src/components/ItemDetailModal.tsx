import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Check, Copy, Download, ExternalLink, Eye, Heart, ImagePlus, Minus, Pencil, Plus, Trash2, X } from 'lucide-react';
import { api, isDemoMode, mediaUrl } from '../api/client';
import FallbackImage from './FallbackImage';
import PromptTemplatePanel from './PromptTemplatePanel';
import type { ClusterRecord, ImageRecord, ItemDetail, NanobananaSourceItem, PromptImageGenerationRunRecord, TagRecord } from '../types';
import { copyTextToClipboard } from '../utils/clipboard';
import { downloadBlobFromUrl } from '../utils/downloads';
import { imageDisplayPaths, imageHeroPaths, selectPrimaryImage } from '../utils/images';
import type { Translator } from '../utils/i18n';
import { PROMPT_LANGUAGE_LABELS, resolvePromptText, type PromptLanguage } from '../utils/prompts';

const LANG_LABELS: Record<string, string> = {
  ...PROMPT_LANGUAGE_LABELS,
  en: 'ENG',
};
const promptDisplayOrder = ['en', 'zh_hant', 'zh_hans'];
const IMAGE_VIEWER_MIN_SCALE = 1;
const IMAGE_VIEWER_MAX_SCALE = 4;
const IMAGE_VIEWER_DOUBLE_TAP_SCALE = 2.4;
const IMAGE_VIEWER_DOUBLE_TAP_DELAY_MS = 260;
const IMAGE_GENERATION_POLL_INTERVAL_MS = 3000;
const IMAGE_GENERATION_POLL_ATTEMPTS = 40;

type DetailPanel = 'prompt' | 'history';

interface GeneratedImageHistoryEntry {
  key: string;
  image: ImageRecord;
  run?: PromptImageGenerationRunRecord;
  source: 'workflow' | 'direct';
  createdAt?: string;
}

function getImageIdentity(image: ImageRecord) {
  return image.thumb_path || image.preview_path || image.original_path || image.id;
}

function imageDownloadUrl(item: ItemDetail, image: ImageRecord) {
  if (isDemoMode) return mediaUrl(image.original_path || image.remote_url || image.preview_path || image.thumb_path);
  return `/api/items/${encodeURIComponent(item.id)}/images/${encodeURIComponent(image.id)}/download`;
}

function imagePathForReference(image: ImageRecord) {
  return image.remote_url || image.original_path || image.preview_path || image.thumb_path || '';
}

function imageUrlForReference(image: ImageRecord) {
  const path = imagePathForReference(image);
  if (!path) return '';
  if (/^https?:\/\//i.test(path)) return path;
  const url = mediaUrl(path);
  if (!url) return '';
  try {
    return new URL(url, window.location.origin).href;
  } catch {
    return url;
  }
}

function imageMimeTypeForReference(image: ImageRecord) {
  const path = imagePathForReference(image).split('?')[0].toLowerCase();
  if (path.endsWith('.png')) return 'image/png';
  if (path.endsWith('.webp')) return 'image/webp';
  if (path.endsWith('.gif')) return 'image/gif';
  if (path.endsWith('.jpg') || path.endsWith('.jpeg')) return 'image/jpeg';
  return undefined;
}

function delay(ms: number) {
  return new Promise(resolve => window.setTimeout(resolve, ms));
}

function createImageGenerationRequestId() {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') return cryptoApi.randomUUID();
  return `req_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function readBatchId(payload: Record<string, unknown> | undefined) {
  const batchId = payload?.batchId || payload?.batch_id;
  return typeof batchId === 'string' && batchId.trim() ? batchId.trim() : '';
}

function imageSourceItem(image: ImageRecord, index: number, t: Translator): NanobananaSourceItem | null {
  const imageUrl = imageUrlForReference(image);
  if (!imageUrl) return null;
  return {
    imageUrl,
    mimeType: imageMimeTypeForReference(image),
    label: index === 0 ? 'primary' : `${t('promptTemplateImageReference')} ${index + 1}`,
    role: index === 0 ? 'subject' : 'style',
    note: image.role === 'reference_image' ? t('referencePhotoOptional') : t('resultImageAlreadySaved'),
  };
}

function imageDownloadFilename(item: ItemDetail, image: ImageRecord) {
  const sourcePath = image.original_path || image.remote_url || image.preview_path || image.thumb_path || '';
  const extensionMatch = sourcePath.match(/\.([a-z0-9]+)(?:$|\?)/i);
  const extension = (extensionMatch?.[1] || 'jpg').toLowerCase().replace('jpeg', 'jpg');
  const safeTitle = item.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 72) || 'prompt-image';
  return `${safeTitle}-${image.id}.${extension}`;
}

function dedupeImages(images: ImageRecord[]) {
  const seenImageKeys = new Set<string>();
  return images.filter(image => {
    const key = getImageIdentity(image);
    if (seenImageKeys.has(key)) return false;
    seenImageKeys.add(key);
    return true;
  });
}

function formatHistoryDate(value?: string) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date);
}

function buildGeneratedImageHistory(images: ImageRecord[], runs: PromptImageGenerationRunRecord[]): GeneratedImageHistoryEntry[] {
  const runByImageId = new Map<string, PromptImageGenerationRunRecord>();
  runs.forEach(run => run.image_ids.forEach(imageId => {
    if (!runByImageId.has(imageId)) runByImageId.set(imageId, run);
  }));
  return images
    .filter(image => (image.role || 'result_image') === 'result_image')
    .map(image => {
      const run = runByImageId.get(image.id);
      return {
        key: `${run?.id || 'direct'}-${image.id}`,
        image,
        run,
        source: run ? 'workflow' : 'direct',
        createdAt: run?.created_at || image.created_at,
      } satisfies GeneratedImageHistoryEntry;
    })
    .sort((left, right) => {
      const leftTime = left.createdAt ? new Date(left.createdAt).getTime() : 0;
      const rightTime = right.createdAt ? new Date(right.createdAt).getTime() : 0;
      return rightTime - leftTime;
    });
}

function clampImageViewerScale(scale: number) {
  return Math.min(IMAGE_VIEWER_MAX_SCALE, Math.max(IMAGE_VIEWER_MIN_SCALE, Number(scale.toFixed(2))));
}

function measureTouchDistance(firstTouch: { clientX: number; clientY: number }, secondTouch: { clientX: number; clientY: number }) {
  return Math.hypot(secondTouch.clientX - firstTouch.clientX, secondTouch.clientY - firstTouch.clientY);
}

function extractErrorDetail(error: unknown): string {
  if (!(error instanceof Error)) return '';
  let message = error.message.trim();
  if (!message) return '';
  try {
    const parsed = JSON.parse(message);
    if (parsed && typeof parsed === 'object' && 'detail' in parsed && parsed.detail) {
      message = String(parsed.detail).trim();
    }
  } catch {
    // Keep raw error text when the payload is not JSON.
  }
  return message;
}

function resolvePromptRecord<T extends { language: string; text: string }>(
  prompts: T[],
  selectedLanguage: string,
  preferredLanguage: PromptLanguage,
): T | undefined {
  const usable = prompts.filter(prompt => prompt.text.trim().length > 0);
  return usable.find(prompt => prompt.language === selectedLanguage)
    || usable.find(prompt => prompt.language === preferredLanguage)
    || usable.find(prompt => prompt.language === 'en')
    || usable[0];
}

function InlineEditableField({
  className,
  value,
  placeholder,
  inputList,
  onCommit,
  editable = true,
  children,
}: {
  className: string;
  value: string;
  placeholder?: string;
  inputList?: string;
  onCommit: (value: string) => void;
  editable?: boolean;
  children?: ReactNode;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);
  const confirm = () => { onCommit(draft); setEditing(false); };
  const cancel = () => { setDraft(value); setEditing(false); };
  if (editing) {
    return (
      <span className={`inline-editable ${className} is-editing`}>
        <input
          value={draft}
          placeholder={placeholder}
          list={inputList}
          autoFocus
          onChange={event => setDraft(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter') confirm();
            if (event.key === 'Escape') cancel();
          }}
        />
        {children}
        <span className="inline-edit-controls">
          <button type="button" className="inline-edit-confirm" onClick={confirm} aria-label="Confirm edit"><Check size={14} /></button>
          <button type="button" className="inline-edit-cancel" onClick={cancel} aria-label="Cancel edit"><X size={14} /></button>
        </span>
      </span>
    );
  }
  if (!editable) {
    return <span className={`inline-editable ${className} is-read-only`}>{value || placeholder}</span>;
  }
  return (
    <span className={`inline-editable ${className}`} onDoubleClick={() => setEditing(true)} tabIndex={0} onKeyDown={event => { if (event.key === 'Enter') setEditing(true); }}>
      {value || placeholder}
    </span>
  );
}

function InlineEditableTextArea({
  className,
  value,
  placeholder,
  onCommit,
  editable = true,
}: {
  className: string;
  value: string;
  placeholder?: string;
  onCommit: (value: string) => void;
  editable?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);
  const confirm = () => { onCommit(draft); setEditing(false); };
  const cancel = () => { setDraft(value); setEditing(false); };
  if (editing) {
    return (
      <div className={`inline-editable ${className} is-editing`}>
        <textarea
          value={draft}
          placeholder={placeholder}
          autoFocus
          onChange={event => setDraft(event.target.value)}
          onKeyDown={event => {
            if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') confirm();
            if (event.key === 'Escape') cancel();
          }}
        />
        <span className="inline-edit-controls">
          <button type="button" className="inline-edit-confirm" onClick={confirm} aria-label="Confirm edit"><Check size={14} /></button>
          <button type="button" className="inline-edit-cancel" onClick={cancel} aria-label="Cancel edit"><X size={14} /></button>
        </span>
      </div>
    );
  }
  if (!editable) {
    return <div className={`inline-editable ${className} is-read-only ${value ? '' : 'notes-empty'}`}>{value ? <p>{value}</p> : <span className="add-note-affordance">{placeholder}</span>}</div>;
  }
  return (
    <div className={`inline-editable ${className} ${value ? '' : 'notes-empty'}`} onDoubleClick={() => setEditing(true)} tabIndex={0} onKeyDown={event => { if (event.key === 'Enter') setEditing(true); }}>
      {value ? <p>{value}</p> : <span className="add-note-affordance">{placeholder}</span>}
    </div>
  );
}

export default function ItemDetailModal({
  id,
  duplicateGroup,
  onSelectDuplicateItem,
  t,
  preferredLanguage,
  clusters,
  tags,
  onClose,
  onCopyPrompt,
  onEdit,
  onChanged,
  showMutations = true,
}: {
  id?: string;
  duplicateGroup?: Array<Pick<ItemDetail, 'id' | 'title' | 'prompts'>>;
  onSelectDuplicateItem?: (id: string) => void;
  t: Translator;
  preferredLanguage: PromptLanguage;
  clusters: ClusterRecord[];
  tags: TagRecord[];
  onClose: () => void;
  onCopyPrompt: (success: boolean) => void;
  onEdit: (item: ItemDetail) => void;
  onChanged: () => void;
  showMutations?: boolean;
}) {
  const [item, setItem] = useState<ItemDetail>();
  const [lang, setLang] = useState<string>(preferredLanguage);
  const [addingTag, setAddingTag] = useState(false);
  const [tagQuery, setTagQuery] = useState('');
  const [editingPromptLanguage, setEditingPromptLanguage] = useState<string>();
  const [promptDraft, setPromptDraft] = useState('');
  const [selectedImageIdentity, setSelectedImageIdentity] = useState<string>();
  const [imageViewerOpen, setImageViewerOpen] = useState(false);
  const [imageViewerScale, setImageViewerScale] = useState(1);
  const [generatingImage, setGeneratingImage] = useState(false);
  const [referenceUploading, setReferenceUploading] = useState(false);
  const [selectedReferenceImageIdentities, setSelectedReferenceImageIdentities] = useState<string[]>([]);
  const [imageGenerationFeedback, setImageGenerationFeedback] = useState<{ tone: 'error' | 'success'; message: string } | null>(null);
  const [detailPanel, setDetailPanel] = useState<DetailPanel>('prompt');
  const [generationRuns, setGenerationRuns] = useState<PromptImageGenerationRunRecord[]>([]);
  const [generationRunsLoading, setGenerationRunsLoading] = useState(false);
  const imageViewerScaleRef = useRef(1);
  const imageViewerScrollRef = useRef<HTMLDivElement>(null);
  const referenceUploadInputRef = useRef<HTMLInputElement | null>(null);
  const heroSectionRef = useRef<HTMLElement>(null);
  const pinchGestureRef = useRef<{ distance: number; scale: number } | null>(null);
  const lastViewerTapAtRef = useRef(0);
  const lastDefaultPromptKeyRef = useRef('');
  const lastReferenceDefaultItemIdRef = useRef('');

  useEffect(() => { setLang(preferredLanguage); }, [preferredLanguage, id]);

  useEffect(() => {
    if (!id) return;
    setItem(undefined);
    api.item(id).then(setItem);
  }, [id]);

  const duplicatePromptGroup = useMemo(
    () => (duplicateGroup && duplicateGroup.length > 1 ? duplicateGroup : []),
    [duplicateGroup],
  );

  const refreshGenerationRuns = async (itemId: string) => {
    try {
      setGenerationRuns(await api.promptImageGenerationRuns(itemId));
    } catch {
      setGenerationRuns([]);
    }
  };

  useEffect(() => {
    if (!id) {
      setGenerationRuns([]);
      return;
    }
    let cancelled = false;
    setGenerationRunsLoading(true);
    api.promptImageGenerationRuns(id)
      .then(runs => { if (!cancelled) setGenerationRuns(runs); })
      .catch(() => { if (!cancelled) setGenerationRuns([]); })
      .finally(() => { if (!cancelled) setGenerationRunsLoading(false); });
    return () => { cancelled = true; };
  }, [id]);

  const availablePromptRecords = useMemo(() => {
    if (!item) return [];
    return promptDisplayOrder
      .map(promptLanguage => item.prompts.find(prompt => prompt.language === promptLanguage && prompt.text.trim().length > 0))
      .filter((prompt): prompt is NonNullable<typeof prompt> => Boolean(prompt));
  }, [item]);

  useEffect(() => {
    if (!item || !id) return;
    const defaultPromptKey = `${id}:${preferredLanguage}`;
    if (lastDefaultPromptKeyRef.current === defaultPromptKey) return;
    const nextPrompt = resolvePromptRecord(availablePromptRecords, preferredLanguage, preferredLanguage);
    if (nextPrompt) setLang(nextPrompt.language);
    lastDefaultPromptKeyRef.current = defaultPromptKey;
  }, [item, availablePromptRecords, preferredLanguage, id]);

  const filteredTagSuggestions = useMemo(() => {
    if (!item) return [];
    const existing = new Set(item.tags.map(tag => tag.name));
    const query = tagQuery.trim().toLowerCase();
    return tags
      .filter(tag => !existing.has(tag.name) && (!query || tag.name.toLowerCase().includes(query)))
      .slice(0, 8);
  }, [item, tags, tagQuery]);
  const prompt = item?.prompts.find(promptRecord => promptRecord.language === lang);
  const resolvedPrompt = resolvePromptRecord(availablePromptRecords, lang, preferredLanguage);
  const copyText = prompt?.text || resolvedPrompt?.text || resolvePromptText(item?.prompts, preferredLanguage, item?.title || '');
  const selectedPromptText = (prompt?.text || resolvedPrompt?.text || copyText).trim();
  const uniqueImages = useMemo(() => dedupeImages(item?.images || []), [item?.images]);
  const primaryImage = selectPrimaryImage(uniqueImages);
  const activeImage = uniqueImages.find(image => getImageIdentity(image) === selectedImageIdentity) || primaryImage;
  const directReferenceCandidates = useMemo(() => {
    return [...uniqueImages].sort((left, right) => {
      const leftRank = left.role === 'reference_image' ? 0 : 1;
      const rightRank = right.role === 'reference_image' ? 0 : 1;
      return leftRank - rightRank;
    });
  }, [uniqueImages]);
  const selectedDirectReferenceImages = useMemo(() => {
    const selected = new Set(selectedReferenceImageIdentities);
    return directReferenceCandidates.filter(image => selected.has(getImageIdentity(image)));
  }, [directReferenceCandidates, selectedReferenceImageIdentities]);
  const generatedImageHistoryEntries = useMemo(() => buildGeneratedImageHistory(uniqueImages, generationRuns), [uniqueImages, generationRuns]);
  useEffect(() => {
    setSelectedImageIdentity(current => {
      const availableImageIdentities = new Set(uniqueImages.map(image => getImageIdentity(image)));
      if (current && availableImageIdentities.has(current)) return current;
      return primaryImage ? getImageIdentity(primaryImage) : undefined;
    });
    setImageViewerOpen(false);
    setImageViewerScale(1);
  }, [item?.id, uniqueImages, primaryImage?.id, primaryImage?.original_path, primaryImage?.preview_path, primaryImage?.thumb_path]);
  useEffect(() => {
    imageViewerScaleRef.current = imageViewerScale;
  }, [imageViewerScale]);
  useEffect(() => {
    if (!item || lastReferenceDefaultItemIdRef.current === item.id) return;
    setSelectedReferenceImageIdentities(uniqueImages.filter(image => image.role === 'reference_image').map(image => getImageIdentity(image)));
    lastReferenceDefaultItemIdRef.current = item.id;
  }, [item, uniqueImages]);
  useEffect(() => {
    const availableImageIdentities = new Set(uniqueImages.map(image => getImageIdentity(image)));
    setSelectedReferenceImageIdentities(current => current.filter(identity => availableImageIdentities.has(identity)));
  }, [uniqueImages]);

  if (!id) return null;

  const toggleFavorite = () => {
    if (!item) return;
    api.favorite(item.id).then(updated => { setItem(updated); onChanged(); });
  };
  const commitInlineUpdate = async (payload: Record<string, unknown>) => {
    if (!item) return;
    const updated = await api.updateItem(item.id, payload);
    setItem(updated);
    onChanged();
  };
  const handleCopyPrompt = async (text = copyText) => {
    const copied = await copyTextToClipboard(text);
    onCopyPrompt(copied);
  };
  const toggleDirectReferenceImage = (image: ImageRecord) => {
    const identity = getImageIdentity(image);
    setSelectedReferenceImageIdentities(current => (
      current.includes(identity)
        ? current.filter(existing => existing !== identity)
        : [...current, identity]
    ));
    setImageGenerationFeedback(null);
  };
  const handleUploadDirectReferenceImage = async (files: FileList | null) => {
    if (!item) return;
    const file = Array.from(files || []).find(candidate => candidate.type.startsWith('image/'));
    if (referenceUploadInputRef.current) referenceUploadInputRef.current.value = '';
    if (!file) {
      setImageGenerationFeedback({ tone: 'error', message: t('imageFileOnly') });
      return;
    }
    setReferenceUploading(true);
    setImageGenerationFeedback(null);
    try {
      const uploaded = await api.uploadImage(item.id, file, 'reference_image');
      const uploadedIdentity = getImageIdentity(uploaded);
      const updated = await api.item(item.id);
      setItem(updated);
      setSelectedReferenceImageIdentities(current => Array.from(new Set([...current, uploadedIdentity])));
      setSelectedImageIdentity(uploadedIdentity);
      onChanged();
    } catch (error) {
      setImageGenerationFeedback({ tone: 'error', message: extractErrorDetail(error) || t('saveFailed') });
    } finally {
      setReferenceUploading(false);
    }
  };
  const handleGenerateImage = async () => {
    if (!item || generatingImage) return;
    const promptText = selectedPromptText;
    if (!promptText) {
      setImageGenerationFeedback({ tone: 'error', message: t('imageGenerationNoPrompt') });
      return;
    }
    setGeneratingImage(true);
    setImageGenerationFeedback(null);
    try {
      const sourceItems = selectedDirectReferenceImages
        .map((image, index) => imageSourceItem(image, index, t))
        .filter((sourceItem): sourceItem is NanobananaSourceItem => Boolean(sourceItem));
      const result = await api.generateItemImage(item.id, {
        promptText,
        promptLanguage: lang,
        idempotencyKey: `${item.id}:nanobanana-images:v1:user-${createImageGenerationRequestId()}`,
        wait: false,
        ...(sourceItems.length > 0 ? { sourceItems } : {}),
      });
      let storedImages = result.stored_images;
      const batchId = readBatchId(result.create);
      if (storedImages.length === 0 && !batchId) {
        throw new Error(t('imageGenerationUnavailable'));
      }
      if (storedImages.length === 0 && batchId) {
        setImageGenerationFeedback({ tone: 'success', message: t('imageGenerationQueued') });
        for (let attempt = 0; attempt < IMAGE_GENERATION_POLL_ATTEMPTS; attempt += 1) {
          await delay(IMAGE_GENERATION_POLL_INTERVAL_MS);
          const status = await api.itemImageGenerationStatus(item.id, batchId);
          storedImages = status.stored_images;
          if (storedImages.length > 0) break;
          const nestedBatch = status.batch.batch;
          const nestedStatus = typeof nestedBatch === 'object' && nestedBatch !== null && 'status' in nestedBatch
            ? (nestedBatch as { status?: unknown }).status
            : undefined;
          const batchStatus = String(nestedStatus || status.batch.status || '');
          if (batchStatus === 'failed') throw new Error(t('imageGenerationUnavailable'));
        }
      }
      const updated = await api.item(item.id);
      setItem(updated);
      const newestImage = updated.images[updated.images.length - 1];
      if (newestImage) setSelectedImageIdentity(getImageIdentity(newestImage));
      void refreshGenerationRuns(item.id);
      onChanged();
      setImageGenerationFeedback({ tone: 'success', message: storedImages.length > 0 ? t('imageGenerationComplete') : t('imageGenerationQueued') });
    } catch (error) {
      setImageGenerationFeedback({ tone: 'error', message: extractErrorDetail(error) || t('imageGenerationUnavailable') });
    } finally {
      setGeneratingImage(false);
    }
  };
  const commitPrompt = (language: string, text: string) => {
    if (!item) return;
    const merged = new Map(item.prompts.map(existing => [existing.language, existing.text]));
    if (text.trim()) merged.set(language, text.trim());
    else merged.delete(language);
    const orderedPromptTexts = promptDisplayOrder.map(promptLanguage => ({ promptLanguage, text: merged.get(promptLanguage)?.trim() || '' }));
    const primaryLanguage = orderedPromptTexts.find(nextPrompt => nextPrompt.text)?.promptLanguage;
    const prompts = orderedPromptTexts
      .map(nextPrompt => ({ language: nextPrompt.promptLanguage, text: nextPrompt.text, is_primary: nextPrompt.promptLanguage === primaryLanguage }))
      .filter(nextPrompt => nextPrompt.text);
    commitInlineUpdate({ prompts });
  };
  const startPromptEdit = (language: string, text: string) => {
    setEditingPromptLanguage(language);
    setPromptDraft(text);
  };
  const cancelPromptEdit = () => {
    setEditingPromptLanguage(undefined);
    setPromptDraft('');
  };
  const confirmPromptEdit = () => {
    if (!editingPromptLanguage) return;
    commitPrompt(editingPromptLanguage, promptDraft);
    cancelPromptEdit();
  };
  const unlinkTag = (tagName: string) => {
    if (!item) return;
    commitInlineUpdate({ tags: item.tags.filter(tag => tag.name !== tagName).map(tag => tag.name) });
  };
  const addTag = (tagName: string) => {
    if (!item) return;
    const nextTag = tagName.trim();
    if (!nextTag) return;
    const nextTags = Array.from(new Set([...item.tags.map(tag => tag.name), nextTag]));
    commitInlineUpdate({ tags: nextTags });
    setAddingTag(false);
    setTagQuery('');
  };
  const openImageViewer = () => {
    if (!activeImage) return;
    pinchGestureRef.current = null;
    lastViewerTapAtRef.current = 0;
    setImageViewerScale(1);
    setImageViewerOpen(true);
  };
  const closeImageViewer = () => {
    pinchGestureRef.current = null;
    lastViewerTapAtRef.current = 0;
    setImageViewerOpen(false);
    setImageViewerScale(1);
  };
  const setImageViewerScaleAroundPoint = (nextScale: number, pointX?: number, pointY?: number) => {
    const clampedScale = clampImageViewerScale(nextScale);
    const scrollElement = imageViewerScrollRef.current;
    if (!scrollElement || pointX === undefined || pointY === undefined) {
      setImageViewerScale(clampedScale);
      return;
    }
    const rect = scrollElement.getBoundingClientRect();
    const offsetX = pointX - rect.left;
    const offsetY = pointY - rect.top;
    const anchorX = scrollElement.scrollLeft + offsetX;
    const anchorY = scrollElement.scrollTop + offsetY;
    const scaleRatio = clampedScale / imageViewerScaleRef.current;
    setImageViewerScale(clampedScale);
    requestAnimationFrame(() => {
      const currentScrollElement = imageViewerScrollRef.current;
      if (!currentScrollElement) return;
      currentScrollElement.scrollLeft = Math.max(0, anchorX * scaleRatio - offsetX);
      currentScrollElement.scrollTop = Math.max(0, anchorY * scaleRatio - offsetY);
    });
  };
  const toggleImageViewerZoom = (pointX?: number, pointY?: number) => {
    const nextScale = imageViewerScaleRef.current > 1.4 ? 1 : IMAGE_VIEWER_DOUBLE_TAP_SCALE;
    setImageViewerScaleAroundPoint(nextScale, pointX, pointY);
  };
  const nudgeImageViewerScale = (delta: number) => {
    setImageViewerScale(scale => clampImageViewerScale(scale + delta));
  };
  const handleImageViewerTouchStart = (event: React.TouchEvent<HTMLDivElement>) => {
    if (event.touches.length === 2) {
      pinchGestureRef.current = {
        distance: measureTouchDistance(event.touches[0], event.touches[1]),
        scale: imageViewerScaleRef.current,
      };
      return;
    }
    if (event.touches.length !== 1) return;
    const now = Date.now();
    if (now - lastViewerTapAtRef.current < IMAGE_VIEWER_DOUBLE_TAP_DELAY_MS) {
      event.preventDefault();
      toggleImageViewerZoom(event.touches[0].clientX, event.touches[0].clientY);
      lastViewerTapAtRef.current = 0;
      return;
    }
    lastViewerTapAtRef.current = now;
  };
  const handleImageViewerTouchMove = (event: React.TouchEvent<HTMLDivElement>) => {
    if (event.touches.length !== 2 || !pinchGestureRef.current) return;
    event.preventDefault();
    const distance = measureTouchDistance(event.touches[0], event.touches[1]);
    const centerX = (event.touches[0].clientX + event.touches[1].clientX) / 2;
    const centerY = (event.touches[0].clientY + event.touches[1].clientY) / 2;
    const scaleRatio = distance / pinchGestureRef.current.distance;
    setImageViewerScaleAroundPoint(pinchGestureRef.current.scale * scaleRatio, centerX, centerY);
  };
  const handleImageViewerTouchEnd = () => {
    pinchGestureRef.current = null;
  };
  const handleDownloadImage = async (image: ImageRecord, event?: { preventDefault?: () => void; stopPropagation: () => void }) => {
    event?.preventDefault?.();
    event?.stopPropagation();
    if (!item) return;
    const href = imageDownloadUrl(item, image);
    if (!href) return;
    try {
      await downloadBlobFromUrl(href, imageDownloadFilename(item, image));
    } catch (error) {
      window.alert(error instanceof Error && error.message ? error.message : t('saveFailed'));
    }
  };
  const handleDeleteImage = async (image: ImageRecord, event?: { preventDefault?: () => void; stopPropagation: () => void }) => {
    event?.preventDefault?.();
    event?.stopPropagation();
    if (!item || !window.confirm(t('deleteImageConfirm'))) return;
    try {
      const updated = await api.deleteImage(item.id, image.id);
      const nextImages = dedupeImages(updated.images);
      const nextActiveImage = nextImages.find(candidate => getImageIdentity(candidate) !== getImageIdentity(image)) || selectPrimaryImage(nextImages);
      setItem(updated);
      setSelectedImageIdentity(nextActiveImage ? getImageIdentity(nextActiveImage) : undefined);
      void refreshGenerationRuns(item.id);
      setImageViewerOpen(false);
      onChanged();
    } catch (error) {
      window.alert(error instanceof Error && error.message ? error.message : t('imageDeleteFailed'));
    }
  };
  const focusGeneratedImage = (image: ImageRecord) => {
    setSelectedImageIdentity(getImageIdentity(image));
    window.requestAnimationFrame(() => heroSectionRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' }));
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="detail modal polished-modal" onClick={e => e.stopPropagation()}>
        {!item ? (
          <p className="modal-loading">{t('loading')}</p>
        ) : (
          <div className="modal-content-enter" key={item.id}>
            <div className="detail-layout">
              <section className="modal-hero" ref={heroSectionRef}>
                {activeImage ? (
                  <button type="button" className="hero-image-button" onClick={openImageViewer} aria-label={t('openImageDetailViewer')}>
                    <FallbackImage
                      className="hero-image"
                      paths={imageHeroPaths(activeImage)}
                      alt={item.title}
                      fallback={<span className="placeholder hero-image image-load-fallback">{t('noImage')}</span>}
                    />
                  </button>
                ) : (
                  <div className="placeholder hero-image">{t('noImage')}</div>
                )}
                {activeImage && (
                  <div className="detail-image-actions" onClick={event => event.stopPropagation()}>
                    <button type="button" className="modal-icon-button detail-image-action" onClick={event => handleDownloadImage(activeImage, event)} aria-label={t('downloadImage')} title={t('downloadImage')}>
                      <Download size={17} />
                    </button>
                    {showMutations && (
                      <button type="button" className="modal-icon-button detail-image-action is-danger" onClick={event => handleDeleteImage(activeImage, event)} aria-label={t('deleteImage')} title={t('deleteImage')}>
                        <Trash2 size={17} />
                      </button>
                    )}
                  </div>
                )}
                <div className="mobile-hero-actions" aria-label={t('itemActions')}>
                  <button className="modal-icon-button mobile-hero-close" onClick={onClose} aria-label={t('close')}>
                    <X size={20} />
                  </button>
                  {showMutations && (
                    <span className="mobile-hero-primary-actions">
                      <button className="modal-icon-button favorite-button" onClick={toggleFavorite} aria-label={item.favorite ? t('saved') : t('favorite')}>
                        <Heart size={18} fill={item.favorite ? 'currentColor' : 'none'} />
                      </button>
                      <button className="modal-icon-button edit-button" onClick={() => onEdit(item)} aria-label={t('edit')}>
                        <Pencil size={18} />
                      </button>
                    </span>
                  )}
                </div>
                {uniqueImages.length > 1 && (
                  <div className="rail glass-rail">
                    {uniqueImages.map(img => (
                      <button
                        type="button"
                        key={getImageIdentity(img)}
                        className={`glass-rail-thumb ${getImageIdentity(img) === getImageIdentity(activeImage || img) ? 'active' : ''}`}
                        onClick={() => setSelectedImageIdentity(getImageIdentity(img))}
                        aria-label={t('openImageDetailViewer')}
                      >
                        <FallbackImage paths={imageDisplayPaths(img)} alt="" fallback={<span className="thumb-fallback">{t('noImage')}</span>} />
                      </button>
                    ))}
                  </div>
                )}
              </section>

              <aside className="detail-side">
                <div className="detail-side-actions">
                  <span className="detail-side-primary-actions">
                    {showMutations && <button className="modal-icon-button favorite-button" onClick={toggleFavorite} aria-label={item.favorite ? t('saved') : t('favorite')}>
                      <Heart size={18} fill={item.favorite ? 'currentColor' : 'none'} />
                    </button>}
                    {showMutations && <button className="modal-icon-button edit-button" onClick={() => onEdit(item)} aria-label={t('edit')}>
                      <Pencil size={18} />
                    </button>}
                  </span>
                  <button className="modal-icon-button close" onClick={onClose} aria-label={t('close')}>
                    <X size={20} />
                  </button>
                </div>
                <InlineEditableField className="collection-inline-edit" value={item.cluster?.name || ''} placeholder={t('unclustered')} inputList="detail-collection-suggestions" onCommit={value => commitInlineUpdate({ cluster_name: value.trim() || null })} editable={showMutations}>
                  <datalist id="detail-collection-suggestions">
                    {clusters.map(collection => <option key={collection.id} value={collection.name} />)}
                  </datalist>
                </InlineEditableField>
                <h2>
                  <InlineEditableField className="title-inline-edit" value={item.title} placeholder={t('titlePlaceholder')} onCommit={value => commitInlineUpdate({ title: value.trim() || item.title })} editable={showMutations} />
                </h2>
                <p className="muted metadata-row">
                  <InlineEditableField className="metadata-inline-edit" value={item.model || t('defaultModel')} placeholder={t('imageGeneratedFrom')} onCommit={value => commitInlineUpdate({ model: value.trim() || item.model })} editable={showMutations} />
                  <span>·</span>
                  <InlineEditableField className="metadata-inline-edit" value={`@${item.author || 'User'}`} placeholder="@User" onCommit={value => commitInlineUpdate({ author: value.replace(/^@/, '').trim() || 'User' })} editable={showMutations} />
                  {item.source_url && (
                    <a className="source-icon-link" href={item.source_url} target="_blank" rel="noreferrer" aria-label={t('source')}>
                      <ExternalLink size={16} />
                    </a>
                  )}
                </p>

                {duplicatePromptGroup.length > 0 && (
                  <div className="detail-duplicate-tabs tabs" role="tablist" aria-label="Prompt variants">
                    {duplicatePromptGroup.map((variant, index) => (
                      <button
                        type="button"
                        role="tab"
                        key={variant.id}
                        aria-selected={variant.id === item.id}
                        className={variant.id === item.id ? 'active' : ''}
                        onClick={() => {
                          if (variant.id !== item.id) onSelectDuplicateItem?.(variant.id);
                        }}
                        title={variant.title}
                      >
                        {`Prompt ${index + 1}`}
                      </button>
                    ))}
                  </div>
                )}

                <div className="detail-panel-tabs tabs" role="tablist" aria-label={t('generatedImagePanel')}>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={detailPanel === 'prompt'}
                    className={detailPanel === 'prompt' ? 'active' : ''}
                    onClick={() => setDetailPanel('prompt')}
                  >
                    {t('promptText')}
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={detailPanel === 'history'}
                    className={detailPanel === 'history' ? 'active' : ''}
                    onClick={() => setDetailPanel('history')}
                  >
                    {t('generatedImagesHistory')} <span>{generatedImageHistoryEntries.length}</span>
                  </button>
                </div>

                {detailPanel === 'prompt' ? (
                  <>
                    <div className="prompt-blocks" aria-label={t('promptLanguage')}>
                      {(() => {
                        return (
                          <section className="prompt-block prompt-panel active">
                        <header className="prompt-block-header">
                          <div className="prompt-language-tabs tabs" role="tablist" aria-label={t('promptLanguage')}>
                            {promptDisplayOrder.map(promptLanguage => {
                              const tabPrompt = item.prompts.find(prompt => prompt.language === promptLanguage);
                              return (
                                <button
                                  type="button"
                                  role="tab"
                                  aria-selected={lang === promptLanguage}
                                  className={`prompt-language-tab ${lang === promptLanguage ? 'active' : ''}`}
                                  onClick={() => { setLang(promptLanguage); cancelPromptEdit(); }}
                                  title={tabPrompt?.text.trim() ? undefined : t('promptText')}
                                  key={promptLanguage}
                                >
                                  {LANG_LABELS[promptLanguage] || promptLanguage}
                                </button>
                              );
                            })}
                          </div>
                          <span className="prompt-block-actions">
                            <button type="button" className="prompt-copy-icon" onClick={() => handleCopyPrompt(prompt?.text || '')} aria-label={t('copyPrompt')} disabled={!prompt?.text}>
                              <Copy size={15} />
                            </button>
                            {showMutations && <button type="button" className="prompt-edit-icon" onClick={() => startPromptEdit(lang, prompt?.text || '')} aria-label={t('edit')}>
                              <Pencil size={15} />
                            </button>}
                          </span>
                        </header>
                        <div className="prompt-panel-body">
                          {editingPromptLanguage === lang ? (
                            <>
                              <textarea
                                className="prompt-edit-textarea"
                                value={promptDraft}
                                placeholder={t('promptText')}
                                autoFocus
                                onChange={event => setPromptDraft(event.target.value)}
                                onKeyDown={event => {
                                  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') confirmPromptEdit();
                                  if (event.key === 'Escape') cancelPromptEdit();
                                }}
                              />
                              <span className="prompt-edit-controls">
                                <button type="button" className="inline-edit-confirm" onClick={confirmPromptEdit} aria-label="Confirm edit"><Check size={14} /></button>
                                <button type="button" className="inline-edit-cancel" onClick={cancelPromptEdit} aria-label="Cancel edit"><X size={14} /></button>
                              </span>
                            </>
                          ) : (
                            <div className={`prompt-inline-edit ${prompt?.text ? '' : 'notes-empty'} ${showMutations ? '' : 'is-read-only'}`} onDoubleClick={() => { if (showMutations) startPromptEdit(lang, prompt?.text || ''); }} tabIndex={showMutations ? 0 : undefined} onKeyDown={event => { if (showMutations && event.key === 'Enter') startPromptEdit(lang, prompt?.text || ''); }}>
                              {prompt?.text ? <p>{prompt.text}</p> : <span className="add-note-affordance">{t('promptText')}</span>}
                            </div>
                          )}
                        </div>
                        <div className="prompt-direct-generate-row">
                          <button type="button" className="primary prompt-direct-generate-button" onClick={handleGenerateImage} disabled={generatingImage || !selectedPromptText}>
                            <ImagePlus size={16} />
                            <span>{generatingImage ? t('generatingImage') : t('generateImage')}</span>
                          </button>
                        </div>
                        <section className="prompt-direct-reference-panel" aria-label={t('promptTemplateImageReferences')}>
                          <div className="prompt-direct-reference-head">
                            <div>
                              <strong>{t('promptTemplateImageReferences')}</strong>
                              <span>{selectedDirectReferenceImages.length > 0 ? `${selectedDirectReferenceImages.length} · ${t('promptTemplateImageToImageMode')}` : t('promptTemplateImageReferencesEmpty')}</span>
                            </div>
                            <input
                              ref={referenceUploadInputRef}
                              type="file"
                              accept="image/*"
                              hidden
                              onChange={event => handleUploadDirectReferenceImage(event.currentTarget.files)}
                            />
                            <button type="button" className="secondary prompt-direct-reference-upload" onClick={() => referenceUploadInputRef.current?.click()} disabled={referenceUploading || generatingImage}>
                              <ImagePlus size={14} />
                              <span>{referenceUploading ? t('saving') : t('promptTemplateImageAddReference')}</span>
                            </button>
                          </div>
                          {directReferenceCandidates.length > 0 && (
                            <div className="prompt-direct-reference-list">
                              {directReferenceCandidates.map(image => {
                                const identity = getImageIdentity(image);
                                const selected = selectedReferenceImageIdentities.includes(identity);
                                return (
                                  <button
                                    type="button"
                                    key={identity}
                                    className={`prompt-direct-reference-thumb ${selected ? 'active' : ''}`}
                                    onClick={() => toggleDirectReferenceImage(image)}
                                    disabled={generatingImage || referenceUploading}
                                    title={image.role === 'reference_image' ? t('referencePhotoOptional') : t('resultImageAlreadySaved')}
                                  >
                                    <FallbackImage paths={imageDisplayPaths(image)} alt="" fallback={<span className="thumb-fallback">{t('noImage')}</span>} />
                                    <span>{image.role === 'reference_image' ? t('referencePhotoOptional') : t('resultImageAlreadySaved')}</span>
                                  </button>
                                );
                              })}
                            </div>
                          )}
                        </section>
                        {(generatingImage || imageGenerationFeedback) && (
                          <p className={`prompt-image-feedback ${imageGenerationFeedback?.tone || 'success'}`}>{generatingImage ? t('generatingImage') : imageGenerationFeedback?.message}</p>
                        )}
                      </section>
                        );
                      })()}
                    </div>

                    <PromptTemplatePanel
                      itemId={item.id}
                      fallbackPrompt={copyText}
                      t={t}
                      referenceImages={uniqueImages}
                      onCopyResult={onCopyPrompt}
                      onImageGenerated={result => {
                        setItem(result.item);
                        const newestImage = result.images[result.images.length - 1];
                        if (newestImage) setSelectedImageIdentity(getImageIdentity(newestImage));
                        void refreshGenerationRuns(result.item.id);
                        window.requestAnimationFrame(() => heroSectionRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' }));
                        onChanged();
                      }}
                    />
                  </>
                ) : (
                  <section className="generated-history-panel prompt-block prompt-panel active" aria-label={t('generatedImagesHistory')}>
                    <header className="generated-history-header">
                      <div>
                        <strong>{t('generatedImagesHistory')}</strong>
                        <span>{generationRunsLoading ? t('loading') : `${generatedImageHistoryEntries.length} ${t('generatedImagesCount')}`}</span>
                      </div>
                    </header>
                    {generatedImageHistoryEntries.length > 0 ? (
                      <div className="generated-history-grid">
                        {generatedImageHistoryEntries.map(entry => {
                          const active = activeImage ? getImageIdentity(entry.image) === getImageIdentity(activeImage) : false;
                          const createdAt = formatHistoryDate(entry.createdAt);
                          return (
                            <article className={`generated-history-card ${active ? 'active' : ''}`} key={entry.key}>
                              <button type="button" className="generated-history-thumb" onClick={() => focusGeneratedImage(entry.image)} aria-label={t('openImageDetailViewer')}>
                                <FallbackImage paths={imageDisplayPaths(entry.image)} alt="" fallback={<span className="thumb-fallback">{t('noImage')}</span>} />
                              </button>
                              <div className="generated-history-meta">
                                <strong>{entry.source === 'workflow' ? t('promptTemplateImageRunSaved') : t('generatedImageDirectRun')}</strong>
                                {createdAt && <span>{createdAt}</span>}
                                {entry.run?.job_id && <span>{entry.run.job_id}</span>}
                                {entry.run?.references.length ? <span>{t('promptTemplateImageRunReferences')}: {entry.run.references.length}</span> : null}
                              </div>
                              <div className="generated-history-actions">
                                <button type="button" className="modal-icon-button" onClick={() => focusGeneratedImage(entry.image)} aria-label={t('openImageDetailViewer')} title={t('openImageDetailViewer')}>
                                  <Eye size={15} />
                                </button>
                                <button type="button" className="modal-icon-button" onClick={event => handleDownloadImage(entry.image, event)} aria-label={t('downloadImage')} title={t('downloadImage')}>
                                  <Download size={15} />
                                </button>
                                {showMutations && (
                                  <button type="button" className="modal-icon-button is-danger" onClick={event => handleDeleteImage(entry.image, event)} aria-label={t('deleteImage')} title={t('deleteImage')}>
                                    <Trash2 size={15} />
                                  </button>
                                )}
                              </div>
                            </article>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="generated-history-empty">{t('generatedImagesEmpty')}</p>
                    )}
                  </section>
                )}

                <InlineEditableTextArea className="notes-inline-edit" value={item.notes || ''} placeholder={t('addNote')} onCommit={value => commitInlineUpdate({ notes: value.trim() || null })} editable={showMutations} />

                <div className="tags detail-tags">
                  {item.tags.map(tag => (
                    <span className="detail-tag-chip" key={tag.id}>#{tag.name}{showMutations && <button type="button" className="tag-unlink-button" onClick={() => unlinkTag(tag.name)} aria-label={`Remove ${tag.name}`}><X size={12} /></button>}</span>
                  ))}
                  {showMutations && (addingTag ? (
                    <span className="tag-add-popover">
                      <input className="tag-add-input" autoFocus value={tagQuery} onChange={event => setTagQuery(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') addTag(tagQuery); if (event.key === 'Escape') setAddingTag(false); }} placeholder={t('tags')} />
                      <button type="button" className="inline-edit-confirm" onClick={() => addTag(tagQuery)}><Check size={12} /></button>
                      <button type="button" className="inline-edit-cancel" onClick={() => setAddingTag(false)}><X size={12} /></button>
                      {filteredTagSuggestions.length > 0 && <span className="tag-add-suggestions">{filteredTagSuggestions.map(tag => <button type="button" key={tag.id} onClick={() => addTag(tag.name)}>#{tag.name}</button>)}</span>}
                    </span>
                  ) : (
                    <button type="button" className="add-tag-chip" onClick={() => setAddingTag(true)} aria-label={t('tags')}><Plus size={14} /></button>
                  ))}
                </div>
              </aside>
            </div>
          </div>
        )}
        {imageViewerOpen && activeImage && (
          <div className="detail-image-viewer" onClick={closeImageViewer}>
            <div className="detail-image-viewer-panel" onClick={event => event.stopPropagation()}>
              <div className="detail-image-viewer-head">
                <div>
                  <strong>{t('imageDetailViewer')}</strong>
                  <span>{t('imageDetailViewerHint')}</span>
                </div>
                <div className="detail-image-viewer-actions">
                  <button type="button" className="modal-icon-button detail-image-action" onClick={event => handleDownloadImage(activeImage, event)} aria-label={t('downloadImage')} title={t('downloadImage')}>
                    <Download size={16} />
                  </button>
                  {showMutations && (
                    <button type="button" className="modal-icon-button detail-image-action is-danger" onClick={event => handleDeleteImage(activeImage, event)} aria-label={t('deleteImage')} title={t('deleteImage')}>
                      <Trash2 size={16} />
                    </button>
                  )}
                  <button type="button" className="modal-icon-button" onClick={closeImageViewer} aria-label={t('close')}>
                    <X size={18} />
                  </button>
                </div>
              </div>
              <div className="detail-image-viewer-controls" aria-label={t('constellationControls')}>
                <button type="button" className="modal-icon-button" onClick={() => nudgeImageViewerScale(-0.25)} aria-label={t('zoomOut')} disabled={imageViewerScale <= 1}>
                  <Minus size={16} />
                </button>
                <span>{Math.round(imageViewerScale * 100)}%</span>
                <button type="button" className="modal-icon-button" onClick={() => nudgeImageViewerScale(0.25)} aria-label={t('zoomIn')} disabled={imageViewerScale >= 4}>
                  <Plus size={16} />
                </button>
                <button type="button" className="secondary detail-image-viewer-reset" onClick={() => setImageViewerScale(1)}>
                  {t('resetView')}
                </button>
              </div>
              <div
                ref={imageViewerScrollRef}
                className="detail-image-viewer-scroll"
                tabIndex={0}
                aria-label={t('imageDetailViewerHint')}
                onDoubleClick={event => toggleImageViewerZoom(event.clientX, event.clientY)}
                onTouchStart={handleImageViewerTouchStart}
                onTouchMove={handleImageViewerTouchMove}
                onTouchEnd={handleImageViewerTouchEnd}
                onTouchCancel={handleImageViewerTouchEnd}
              >
                <div className="detail-image-viewer-stage" style={{ width: `${imageViewerScale * 100}%` }}>
                  <FallbackImage
                    className="detail-image-viewer-image"
                    paths={imageHeroPaths(activeImage)}
                    alt={item?.title || ''}
                    fallback={<span className="placeholder image-load-fallback">{t('noImage')}</span>}
                  />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

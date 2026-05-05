import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Copy, RefreshCcw, Sparkles } from 'lucide-react';
import { api } from '../api/client';
import { copyTextToClipboard } from '../utils/clipboard';
import { buildSlotValueRecord, renderMarkedPrompt } from '../utils/promptTemplate';
import type { PromptGenerationSessionRecord, PromptGenerationVariantRecord, PromptImageGenerationOptions, PromptImageGenerationResponse, PromptRenderSegment, PromptTemplateBundle } from '../types';
import type { Translator } from '../utils/i18n';

type LocalPromptPreview = {
  renderedText: string;
  segments: PromptRenderSegment[];
};

type SavedImageGenerationPreset = {
  id: string;
  name: string;
  options: Required<PromptImageGenerationOptions>;
};

type ImageGenerationPhase = 'idle' | 'queued' | 'rendering' | 'success' | 'error';

type ImageGenerationState =
  | { phase: 'idle' }
  | { phase: 'queued' }
  | { phase: 'rendering' }
  | { phase: 'success'; imageCount: number }
  | { phase: 'error'; message: string };

const IMAGE_RESOLUTION_OPTIONS = ['1024x1024', '1536x1024', '1024x1536', '2048x2048', '4096x4096'] as const;
const IMAGE_ASPECT_RATIO_OPTIONS = ['auto', '1:1', '4:3', '3:2', '16:9', '9:16'] as const;
const IMAGE_STYLE_OPTIONS = ['auto', 'cinematic', 'editorial', 'illustration', 'photoreal', 'fantasy art', 'ink & wash'] as const;
const IMAGE_GENERATION_STAGE_DELAY_MS = 2200;
const IMAGE_GENERATION_PRESETS_STORAGE_KEY = 'image-prompt-library.image_generation_presets.v1';
const IMAGE_GENERATION_RECENT_OPTIONS_STORAGE_KEY = 'image-prompt-library.image_generation_recent_options.v1';
const IMAGE_GENERATION_PRESET_LIMIT = 6;
const DEFAULT_IMAGE_GENERATION_OPTIONS: Required<PromptImageGenerationOptions> = {
  resolution: '1024x1024',
  aspect_ratio: '1:1',
  image_count: 1,
  style: 'auto',
};

function isAllowedValue<T extends readonly string[]>(value: unknown, allowedValues: T, fallback: string): string {
  return typeof value === 'string' && allowedValues.includes(value as T[number]) ? value : fallback;
}

function normalizeImageGenerationOptions(value: unknown): Required<PromptImageGenerationOptions> {
  const record = value && typeof value === 'object' ? value as Record<string, unknown> : {};
  const imageCount = typeof record.image_count === 'number' && Number.isFinite(record.image_count)
    ? Math.max(1, Math.min(4, Math.round(record.image_count)))
    : DEFAULT_IMAGE_GENERATION_OPTIONS.image_count;
  return {
    resolution: isAllowedValue(record.resolution, IMAGE_RESOLUTION_OPTIONS, DEFAULT_IMAGE_GENERATION_OPTIONS.resolution),
    aspect_ratio: isAllowedValue(record.aspect_ratio, IMAGE_ASPECT_RATIO_OPTIONS, DEFAULT_IMAGE_GENERATION_OPTIONS.aspect_ratio),
    image_count: imageCount,
    style: isAllowedValue(record.style, IMAGE_STYLE_OPTIONS, DEFAULT_IMAGE_GENERATION_OPTIONS.style),
  };
}

function loadRecentImageGenerationOptions(): Required<PromptImageGenerationOptions> | null {
  try {
    const raw = window.localStorage.getItem(IMAGE_GENERATION_RECENT_OPTIONS_STORAGE_KEY);
    if (!raw) return null;
    return normalizeImageGenerationOptions(JSON.parse(raw));
  } catch {
    return null;
  }
}

function loadSavedImageGenerationPresets(): SavedImageGenerationPreset[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(IMAGE_GENERATION_PRESETS_STORAGE_KEY) || '[]');
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map(entry => {
        const record = entry && typeof entry === 'object' ? entry as Record<string, unknown> : null;
        if (!record || typeof record.id !== 'string' || typeof record.name !== 'string') return null;
        return {
          id: record.id,
          name: record.name.trim(),
          options: normalizeImageGenerationOptions(record.options),
        };
      })
      .filter((entry): entry is SavedImageGenerationPreset => Boolean(entry && entry.name));
  } catch {
    return [];
  }
}

function sameImageGenerationOptions(
  left: Required<PromptImageGenerationOptions>,
  right: Required<PromptImageGenerationOptions>,
) {
  return left.resolution === right.resolution
    && left.aspect_ratio === right.aspect_ratio
    && left.image_count === right.image_count
    && left.style === right.style;
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

function statusLabel(status: string, t: Translator) {
  if (status === 'ready') return t('promptTemplateReady');
  if (status === 'stale') return t('promptTemplateStale');
  return status;
}

function imageGenerationStatusTone(phase: ImageGenerationPhase) {
  if (phase === 'queued') return 'stale';
  if (phase === 'rendering') return 'ready';
  if (phase === 'success') return 'accepted';
  if (phase === 'error') return 'failed';
  return 'ready';
}

function replaceSession(bundle: PromptTemplateBundle | null, session: PromptGenerationSessionRecord): PromptTemplateBundle {
  return {
    template: bundle?.template,
    sessions: [session, ...(bundle?.sessions || []).filter(existing => existing.id !== session.id)],
  };
}

export default function PromptTemplatePanel({
  itemId,
  t,
  onCopyResult,
  onImageGenerated,
}: {
  itemId: string;
  t: Translator;
  onCopyResult: (success: boolean) => void;
  onImageGenerated?: (result: PromptImageGenerationResponse) => void;
}) {
  const [bundle, setBundle] = useState<PromptTemplateBundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [themeKeyword, setThemeKeyword] = useState('');
  const [feedback, setFeedback] = useState<{ tone: 'error' | 'success'; message: string } | null>(null);
  const [generating, setGenerating] = useState(false);
  const [rerolling, setRerolling] = useState(false);
  const [imageGenerationOptions, setImageGenerationOptions] = useState<Required<PromptImageGenerationOptions>>(() => loadRecentImageGenerationOptions() || DEFAULT_IMAGE_GENERATION_OPTIONS);
  const [imageGenerationState, setImageGenerationState] = useState<ImageGenerationState>({ phase: 'idle' });
  const [savedImagePresets, setSavedImagePresets] = useState<SavedImageGenerationPreset[]>(loadSavedImageGenerationPresets);
  const [recentImageGenerationOptions, setRecentImageGenerationOptions] = useState<Required<PromptImageGenerationOptions> | null>(loadRecentImageGenerationOptions);
  const [imagePresetName, setImagePresetName] = useState('');
  const [editorValues, setEditorValues] = useState<Record<string, string>>({});
  const [draftBaseValues, setDraftBaseValues] = useState<Record<string, string>>({});
  const [editingVariantId, setEditingVariantId] = useState('original');
  const [assembledPreview, setAssembledPreview] = useState<LocalPromptPreview | null>(null);
  const [targetedSlotId, setTargetedSlotId] = useState<string | null>(null);
  const slotInputRefs = useRef<Record<string, HTMLTextAreaElement | null>>({});
  const targetedSlotTimerRef = useRef<number | null>(null);
  const imageGenerationTimerRef = useRef<number | null>(null);

  const clearImageGenerationTimer = useCallback(() => {
    if (imageGenerationTimerRef.current) {
      window.clearTimeout(imageGenerationTimerRef.current);
      imageGenerationTimerRef.current = null;
    }
  }, []);

  const loadBundle = useCallback(async () => {
    setLoading(true);
    try {
      const nextBundle = await api.promptTemplate(itemId);
      setBundle(nextBundle);
      setFeedback(null);
    } catch {
      setBundle({ sessions: [] });
    } finally {
      setLoading(false);
    }
  }, [itemId, t]);

  useEffect(() => {
    loadBundle();
  }, [loadBundle]);

  const template = bundle?.template;
  const currentSession = bundle?.sessions?.[0];
  const currentVariants = currentSession?.variants || [];
  const latestVariant = currentVariants[0];
  const slotLookup = useMemo(() => {
    return new Map((template?.slots || []).map(slot => [slot.id, slot]));
  }, [template?.slots]);

  const applyDraftValues = useCallback((nextValues: Record<string, string>, nextVariantId: string) => {
    setEditorValues(nextValues);
    setDraftBaseValues(nextValues);
    setEditingVariantId(nextVariantId);
    setAssembledPreview(null);
    setImageGenerationState({ phase: 'idle' });
  }, []);

  const loadEditorDraft = useCallback((variant?: PromptGenerationVariantRecord | null) => {
    if (!template) return;
    applyDraftValues(buildSlotValueRecord(template.slots, variant), variant?.id || 'original');
  }, [applyDraftValues, template]);

  useEffect(() => {
    if (!template) {
      setEditorValues({});
      setDraftBaseValues({});
      setEditingVariantId('original');
      setAssembledPreview(null);
      return;
    }
    loadEditorDraft(latestVariant);
  }, [template?.id, template?.updated_at, loadEditorDraft]);

  useEffect(() => {
    return () => {
      if (targetedSlotTimerRef.current) window.clearTimeout(targetedSlotTimerRef.current);
      clearImageGenerationTimer();
    };
  }, [clearImageGenerationTimer]);

  const livePreview = useMemo(() => {
    if (!template) return null;
    return renderMarkedPrompt(template.marked_text, editorValues);
  }, [template?.marked_text, editorValues]);

  const changedSlotLabels = useMemo(() => {
    const preview = assembledPreview || livePreview;
    if (!preview) return [];
    return preview.segments
      .filter(segment => segment.type === 'slot' && segment.changed)
      .map(segment => segment.label || segment.slot_id || 'slot');
  }, [assembledPreview, livePreview]);

  const manualEditedSlotCount = useMemo(() => {
    if (!template) return 0;
    return template.slots.reduce((count, slot) => {
      const currentValue = editorValues[slot.id] ?? slot.original_text;
      const baseValue = draftBaseValues[slot.id] ?? slot.original_text;
      return count + (currentValue !== baseValue ? 1 : 0);
    }, 0);
  }, [draftBaseValues, editorValues, template]);

  const imageGenerationBusy = imageGenerationState.phase === 'queued' || imageGenerationState.phase === 'rendering';
  const hasRecentImagePreset = Boolean(recentImageGenerationOptions && !sameImageGenerationOptions(recentImageGenerationOptions, DEFAULT_IMAGE_GENERATION_OPTIONS));
  const activePresetId = useMemo(() => {
    const savedPreset = savedImagePresets.find(preset => sameImageGenerationOptions(preset.options, imageGenerationOptions));
    if (savedPreset) return savedPreset.id;
    if (sameImageGenerationOptions(imageGenerationOptions, DEFAULT_IMAGE_GENERATION_OPTIONS)) return 'default';
    if (recentImageGenerationOptions && sameImageGenerationOptions(imageGenerationOptions, recentImageGenerationOptions)) return 'recent';
    return null;
  }, [imageGenerationOptions, recentImageGenerationOptions, savedImagePresets]);
  const imageGenerationStatusText = useMemo(() => {
    if (imageGenerationState.phase === 'queued') return t('promptTemplateImageQueued');
    if (imageGenerationState.phase === 'rendering') return t('promptTemplateImageRendering');
    if (imageGenerationState.phase === 'success') return `${t('promptTemplateImageReady')} · ${imageGenerationState.imageCount} · ${t('promptTemplateImageFocused')}`;
    if (imageGenerationState.phase === 'error') return imageGenerationState.message;
    return '';
  }, [imageGenerationState, t]);
  const imageGenerationButtonLabel = imageGenerationBusy
    ? imageGenerationState.phase === 'queued'
      ? t('promptTemplateImageQueued')
      : t('promptTemplateGeneratingImage')
    : imageGenerationState.phase === 'error'
      ? t('promptTemplateImageRetry')
      : t('promptTemplateGenerateImage');

  useEffect(() => {
    window.localStorage.setItem(IMAGE_GENERATION_PRESETS_STORAGE_KEY, JSON.stringify(savedImagePresets));
  }, [savedImagePresets]);

  const updateImageGenerationOptions = useCallback((nextOptions: Required<PromptImageGenerationOptions>) => {
    setImageGenerationOptions(nextOptions);
    setImageGenerationState({ phase: 'idle' });
  }, []);

  const handleGenerate = async () => {
    if (!template) return;
    const nextKeyword = themeKeyword.trim();
    if (!nextKeyword) {
      setFeedback({ tone: 'error', message: t('promptTemplateThemePlaceholder') });
      return;
    }
    setGenerating(true);
    setFeedback(null);
    try {
      const session = await api.generatePromptVariant(template.id, nextKeyword);
      setBundle(current => replaceSession(current, session));
      setFeedback({ tone: 'success', message: t('promptTemplateVariantReadyDraftPreserved') });
    } catch (error) {
      setFeedback({ tone: 'error', message: extractErrorDetail(error) || t('promptTemplateUnavailable') });
    } finally {
      setGenerating(false);
    }
  };

  const handleReroll = async () => {
    if (!currentSession) return;
    setRerolling(true);
    setFeedback(null);
    try {
      const session = await api.rerollPromptVariant(currentSession.id, currentSession.variants.map(variant => variant.id));
      setBundle(current => replaceSession(current, session));
      setFeedback({ tone: 'success', message: t('promptTemplateVariantReadyDraftPreserved') });
    } catch (error) {
      setFeedback({ tone: 'error', message: extractErrorDetail(error) || t('promptTemplateUnavailable') });
    } finally {
      setRerolling(false);
    }
  };

  const handleSlotChange = (slotId: string, text: string) => {
    setEditorValues(current => ({ ...current, [slotId]: text }));
    setAssembledPreview(null);
    setImageGenerationState({ phase: 'idle' });
  };

  const handleResetSlot = (slotId: string) => {
    const slot = slotLookup.get(slotId);
    if (!slot) return;
    setEditorValues(current => ({ ...current, [slotId]: slot.original_text }));
    setAssembledPreview(null);
    setImageGenerationState({ phase: 'idle' });
  };

  const handleAssemble = () => {
    if (!livePreview) return;
    setAssembledPreview(livePreview);
    setImageGenerationState({ phase: 'idle' });
  };

  const handleCopyFinal = async () => {
    const nextPreview = assembledPreview || livePreview;
    if (!nextPreview) return;
    if (!assembledPreview) setAssembledPreview(nextPreview);
    const copied = await copyTextToClipboard(nextPreview.renderedText);
    onCopyResult(copied);
    if (!copied) setFeedback({ tone: 'error', message: t('copyFailed') });
  };

  const handleGenerateImage = async () => {
    const nextPreview = assembledPreview || livePreview;
    const promptText = nextPreview?.renderedText.trim() || '';
    if (!promptText) {
      setFeedback({ tone: 'error', message: t('promptTemplateFinalPromptRequired') });
      return;
    }
    if (!assembledPreview) setAssembledPreview(nextPreview);
    clearImageGenerationTimer();
    setImageGenerationState({ phase: 'queued' });
    imageGenerationTimerRef.current = window.setTimeout(() => {
      setImageGenerationState(current => current.phase === 'queued' ? { phase: 'rendering' } : current);
      imageGenerationTimerRef.current = null;
    }, IMAGE_GENERATION_STAGE_DELAY_MS);
    setFeedback(null);
    try {
      const result = await api.generateImageFromPrompt(itemId, promptText, imageGenerationOptions);
      clearImageGenerationTimer();
      window.localStorage.setItem(IMAGE_GENERATION_RECENT_OPTIONS_STORAGE_KEY, JSON.stringify(imageGenerationOptions));
      setRecentImageGenerationOptions(imageGenerationOptions);
      setImageGenerationState({ phase: 'success', imageCount: result.images.length });
      onImageGenerated?.(result);
    } catch (error) {
      clearImageGenerationTimer();
      const message = extractErrorDetail(error) || t('promptTemplateImageUnavailable');
      setImageGenerationState({ phase: 'error', message });
      setFeedback({ tone: 'error', message });
    }
  };

  const handleApplyImagePreset = (options: Required<PromptImageGenerationOptions>) => {
    if (imageGenerationBusy) return;
    updateImageGenerationOptions(options);
  };

  const handleSaveImagePreset = () => {
    const nextName = imagePresetName.trim();
    if (!nextName) {
      setFeedback({ tone: 'error', message: t('promptTemplateImagePresetNameRequired') });
      return;
    }
    setSavedImagePresets(current => {
      const nextPreset: SavedImageGenerationPreset = {
        id: current.find(preset => preset.name.toLowerCase() === nextName.toLowerCase())?.id || `preset-${Date.now()}`,
        name: nextName,
        options: imageGenerationOptions,
      };
      const filtered = current.filter(preset => preset.id !== nextPreset.id && preset.name.toLowerCase() !== nextName.toLowerCase());
      return [nextPreset, ...filtered].slice(0, IMAGE_GENERATION_PRESET_LIMIT);
    });
    setImagePresetName('');
    setFeedback({ tone: 'success', message: `${t('promptTemplateImagePresetSaved')} · ${nextName}` });
  };

  const handleDeleteImagePreset = (presetId: string) => {
    setSavedImagePresets(current => current.filter(preset => preset.id !== presetId));
  };

  const handleApplyVariantChanges = (variant: PromptGenerationVariantRecord) => {
    if (!template) return;
    const changedSlotIds = Array.from(new Set(
      variant.segments
        .filter(segment => segment.type === 'slot' && segment.changed && segment.slot_id)
        .map(segment => segment.slot_id as string),
    ));
    if (changedSlotIds.length === 0) return;
    const variantValues = buildSlotValueRecord(template.slots, variant);
    const nextValues = { ...editorValues };
    for (const slotId of changedSlotIds) {
      if (slotId in variantValues) nextValues[slotId] = variantValues[slotId];
    }
    applyDraftValues(nextValues, variant.id);
    setFeedback({ tone: 'success', message: `${t('promptTemplateAppliedChangedSlots')} · ${changedSlotIds.length} ${t('promptTemplateSlots')}` });
  };

  const handleJumpToSlot = (slotId?: string) => {
    if (!slotId) return;
    const target = slotInputRefs.current[slotId];
    if (!target) return;
    target.scrollIntoView({ block: 'center', behavior: 'smooth' });
    target.focus({ preventScroll: true });
    setTargetedSlotId(slotId);
    if (targetedSlotTimerRef.current) window.clearTimeout(targetedSlotTimerRef.current);
    targetedSlotTimerRef.current = window.setTimeout(() => setTargetedSlotId(current => current === slotId ? null : current), 1800);
  };

  const renderPreviewSegment = (segment: PromptRenderSegment, key: string) => {
    const clickable = segment.type === 'slot' && Boolean(segment.slot_id);
    const className = segment.type === 'slot' && segment.changed ? 'prompt-remix-segment is-changed' : 'prompt-remix-segment';
    if (!clickable) return <span key={key} className={className}>{segment.text}</span>;
    return (
      <button
        key={key}
        type="button"
        className={`${className} prompt-remix-segment-button`}
        onClick={() => handleJumpToSlot(segment.slot_id)}
        title={segment.label || segment.slot_id || undefined}
      >
        {segment.text}
      </button>
    );
  };

  if (loading || !template) return null;

  return (
    <section className="prompt-remix-panel" aria-label={t('aiRewrite')}>
      <header className="prompt-remix-header">
        <div>
          <h3>{t('aiRewrite')}</h3>
          <p>{t('aiRewriteHelp')}</p>
        </div>
      </header>

      {feedback && <p className={`prompt-remix-feedback ${feedback.tone}`}>{feedback.message}</p>}

      <>
          <div className="prompt-remix-meta-row">
            <span className={`prompt-remix-status is-${template.status}`}>{statusLabel(template.status, t)}</span>
            <span>{template.slots.length} {t('promptTemplateSlots')}</span>
            {typeof template.analysis_confidence === 'number' && <span>{Math.round(template.analysis_confidence * 100)}%</span>}
          </div>

          <div className="prompt-remix-slot-list">
            {template.slots.map(slot => (
              <span key={slot.id} className="prompt-remix-slot-chip">{slot.label}</span>
            ))}
          </div>

          <label className="prompt-remix-label">{t('promptTemplateThemeKeyword')}</label>
          <div className="prompt-remix-actions">
            <input
              className="prompt-remix-input"
              value={themeKeyword}
              onChange={event => setThemeKeyword(event.target.value)}
              placeholder={t('promptTemplateThemePlaceholder')}
            />
            <button type="button" className="primary" onClick={handleGenerate} disabled={generating || template.status !== 'ready'}>
              <Sparkles size={15} />
              <span>{generating ? t('promptTemplateGenerating') : t('promptTemplateGenerate')}</span>
            </button>
            <button type="button" className="secondary" onClick={handleReroll} disabled={!currentSession || rerolling || template.status !== 'ready'}>
              <RefreshCcw size={15} />
              <span>{rerolling ? t('promptTemplateGenerating') : t('promptTemplateReroll')}</span>
            </button>
          </div>

          {currentSession ? (
            <div className="prompt-remix-variants">
              <div className="prompt-remix-session-bar">
                <strong>{currentSession.theme_keyword}</strong>
                {changedSlotLabels.length > 0 && <span>{t('promptTemplateChangedParts')}: {changedSlotLabels.join(' / ')}</span>}
              </div>
              {currentVariants.map(variant => {
                const changedSegments = variant.segments.filter(segment => segment.type === 'slot' && segment.changed);
                const changedSlotIds = Array.from(new Set(
                  changedSegments
                    .map(segment => segment.slot_id)
                    .filter((slotId): slotId is string => Boolean(slotId)),
                ));
                const variantValues = buildSlotValueRecord(template.slots, variant);
                const applyImpactCount = changedSlotIds.reduce((count, slotId) => {
                  const slot = slotLookup.get(slotId);
                  const currentValue = editorValues[slotId] ?? slot?.original_text ?? '';
                  return count + (currentValue !== variantValues[slotId] ? 1 : 0);
                }, 0);
                const replaceImpactCount = template.slots.reduce((count, slot) => {
                  const currentValue = editorValues[slot.id] ?? slot.original_text;
                  return count + (currentValue !== variantValues[slot.id] ? 1 : 0);
                }, 0);
                const accepted = variant.accepted || currentSession.accepted_variant_id === variant.id;
                const isEditingDraft = editingVariantId === variant.id;
                return (
                  <article key={variant.id} className={`prompt-remix-variant ${accepted ? 'is-accepted' : ''}`}>
                    <div className="prompt-remix-variant-head">
                      <strong>v{variant.iteration}</strong>
                      <div className="prompt-remix-variant-badges">
                        {isEditingDraft && <span className="prompt-remix-status is-ready">{t('promptTemplateEditingDraft')}</span>}
                        {accepted && <span className="prompt-remix-status is-accepted">{t('promptTemplateAccepted')}</span>}
                      </div>
                    </div>
                    {variant.change_summary && (
                      <p className="prompt-remix-summary">
                        <strong>{t('promptTemplateChangeSummary')}:</strong> {variant.change_summary}
                      </p>
                    )}
                    <div className="prompt-remix-preview">
                      {variant.segments.map((segment, index) => (
                        <span
                          key={`${variant.id}-${index}`}
                          className={segment.type === 'slot' && segment.changed ? 'prompt-remix-segment is-changed' : 'prompt-remix-segment'}
                          title={segment.type === 'slot' && segment.changed ? `${segment.label || segment.slot_id}: ${segment.before || ''}` : undefined}
                        >
                          {segment.text}
                        </span>
                      ))}
                    </div>
                    {changedSegments.length > 0 && (
                      <ul className="prompt-remix-change-list">
                        {changedSegments.map(segment => (
                          <li key={`${variant.id}-${segment.slot_id}`}>
                            <strong>{segment.label || segment.slot_id}</strong>
                            <span>{segment.before}</span>
                            <span>{segment.text}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                    <div className="prompt-remix-actions">
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => handleApplyVariantChanges(variant)}
                        disabled={applyImpactCount === 0}
                      >
                        <span>{t('promptTemplateApplyChangedSlots')} ({applyImpactCount})</span>
                      </button>
                      <button type="button" className="secondary" onClick={() => loadEditorDraft(variant)} disabled={isEditingDraft || replaceImpactCount === 0}>
                        <span>{isEditingDraft ? t('promptTemplateEditingDraft') : `${t('promptTemplateReplaceAllSlots')} (${replaceImpactCount})`}</span>
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <p className="prompt-remix-empty">{t('promptTemplateNoVariants')}</p>
          )}

          <section className="prompt-remix-editor" aria-label={t('promptTemplateSlotEditor')}>
            <div className="prompt-remix-editor-head">
              <div>
                <h4>{t('promptTemplateSlotEditor')}</h4>
                <p>{t('promptTemplateSlotEditorHelp')}</p>
              </div>
              <div className="prompt-remix-editor-statuses">
                <span className="prompt-remix-status is-ready">
                  {editingVariantId === 'original' ? t('promptTemplateOriginalValue') : t('promptTemplateEditingDraft')}
                </span>
                {manualEditedSlotCount > 0 && (
                  <span className="prompt-remix-status is-dirty">
                    {t('promptTemplateManualEdits')} · {manualEditedSlotCount} {t('promptTemplateSlots')}
                  </span>
                )}
                <button type="button" className="primary prompt-remix-generate-image-shortcut" onClick={handleGenerateImage} disabled={imageGenerationBusy}>
                  <Sparkles size={15} />
                  <span>{imageGenerationButtonLabel}</span>
                </button>
              </div>
            </div>
            <div className="prompt-remix-editor-grid">
              {template.slots.map(slot => {
                const currentValue = editorValues[slot.id] ?? slot.original_text;
                const changed = currentValue !== slot.original_text;
                const rowCount = Math.min(6, Math.max(2, Math.ceil(Math.max(currentValue.length, slot.original_text.length) / 60)));
                return (
                  <article
                    key={slot.id}
                    className={`prompt-remix-editor-card ${changed ? 'is-changed' : ''} ${targetedSlotId === slot.id ? 'is-targeted' : ''}`}
                  >
                    <div className="prompt-remix-editor-card-head">
                      <div>
                        <strong>{slot.label}</strong>
                        {slot.instruction && <p>{slot.instruction}</p>}
                      </div>
                      <button type="button" className="secondary prompt-remix-reset" onClick={() => handleResetSlot(slot.id)} disabled={!changed}>
                        <span>{t('promptTemplateResetSlot')}</span>
                      </button>
                    </div>
                    <textarea
                      className="prompt-remix-textarea"
                      rows={rowCount}
                      value={currentValue}
                      onChange={event => handleSlotChange(slot.id, event.target.value)}
                      ref={node => { slotInputRefs.current[slot.id] = node; }}
                    />
                    <div className="prompt-remix-original">
                      <span>{t('promptTemplateOriginalValue')}</span>
                      <p>{slot.original_text}</p>
                    </div>
                  </article>
                );
              })}
            </div>
            <section className="prompt-remix-image-config" aria-label={t('promptTemplateImageSettings')}>
              <div className="prompt-remix-image-config-head">
                <div>
                  <h4>{t('promptTemplateImageSettings')}</h4>
                  <p>{t('promptTemplateImageSettingsHelp')}</p>
                </div>
                {imageGenerationState.phase !== 'idle' && (
                  <span className={`prompt-remix-status is-${imageGenerationStatusTone(imageGenerationState.phase)}`}>
                    {imageGenerationState.phase === 'success' ? t('promptTemplateImageReady') : imageGenerationStatusText}
                  </span>
                )}
              </div>
              <div className="prompt-remix-preset-section">
                <div className="prompt-remix-preset-head">
                  <strong>{t('promptTemplateImagePresets')}</strong>
                  <span>{t('promptTemplateImagePresetsHelp')}</span>
                </div>
                <div className="prompt-remix-preset-list">
                  <button
                    type="button"
                    className={`prompt-remix-preset-chip ${activePresetId === 'default' ? 'active' : ''}`}
                    onClick={() => handleApplyImagePreset(DEFAULT_IMAGE_GENERATION_OPTIONS)}
                    disabled={imageGenerationBusy}
                  >
                    <span>{t('promptTemplateImagePresetDefault')}</span>
                  </button>
                  <button
                    type="button"
                    className={`prompt-remix-preset-chip ${activePresetId === 'recent' ? 'active' : ''}`}
                    onClick={() => recentImageGenerationOptions && handleApplyImagePreset(recentImageGenerationOptions)}
                    disabled={imageGenerationBusy || !hasRecentImagePreset}
                  >
                    <span>{t('promptTemplateImagePresetRecent')}</span>
                  </button>
                  {savedImagePresets.map(preset => (
                    <span key={preset.id} className={`prompt-remix-preset-chip ${activePresetId === preset.id ? 'active' : ''}`}>
                      <button type="button" onClick={() => handleApplyImagePreset(preset.options)} disabled={imageGenerationBusy}>
                        <span>{preset.name}</span>
                      </button>
                      <button
                        type="button"
                        className="prompt-remix-preset-delete"
                        onClick={() => handleDeleteImagePreset(preset.id)}
                        aria-label={`${t('promptTemplateImagePresetDelete')} ${preset.name}`}
                        disabled={imageGenerationBusy}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
                <div className="prompt-remix-preset-form">
                  <input
                    className="prompt-remix-input"
                    value={imagePresetName}
                    onChange={event => setImagePresetName(event.target.value)}
                    placeholder={t('promptTemplateImagePresetNamePlaceholder')}
                    maxLength={32}
                    disabled={imageGenerationBusy}
                  />
                  <button type="button" className="secondary" onClick={handleSaveImagePreset} disabled={imageGenerationBusy}>
                    <span>{t('promptTemplateImagePresetSave')}</span>
                  </button>
                </div>
              </div>
              <div className="prompt-remix-image-config-grid">
                <label className="prompt-remix-select-field">
                  <span>{t('promptTemplateImageAspectRatio')}</span>
                  <select
                    className="prompt-remix-select"
                    value={imageGenerationOptions.aspect_ratio}
                    onChange={event => updateImageGenerationOptions({ ...imageGenerationOptions, aspect_ratio: event.target.value as Required<PromptImageGenerationOptions>['aspect_ratio'] })}
                    disabled={imageGenerationBusy}
                  >
                    {IMAGE_ASPECT_RATIO_OPTIONS.map(option => <option key={option} value={option}>{option}</option>)}
                  </select>
                </label>
                <label className="prompt-remix-select-field">
                  <span>{t('promptTemplateImageResolution')}</span>
                  <select
                    className="prompt-remix-select"
                    value={imageGenerationOptions.resolution}
                    onChange={event => updateImageGenerationOptions({ ...imageGenerationOptions, resolution: event.target.value as Required<PromptImageGenerationOptions>['resolution'] })}
                    disabled={imageGenerationBusy}
                  >
                    {IMAGE_RESOLUTION_OPTIONS.map(option => <option key={option} value={option}>{option}</option>)}
                  </select>
                </label>
                <label className="prompt-remix-select-field">
                  <span>{t('promptTemplateImageStyle')}</span>
                  <select
                    className="prompt-remix-select"
                    value={imageGenerationOptions.style}
                    onChange={event => updateImageGenerationOptions({ ...imageGenerationOptions, style: event.target.value as Required<PromptImageGenerationOptions>['style'] })}
                    disabled={imageGenerationBusy}
                  >
                    {IMAGE_STYLE_OPTIONS.map(option => <option key={option} value={option}>{option}</option>)}
                  </select>
                </label>
                <label className="prompt-remix-select-field">
                  <span>{t('promptTemplateImageCount')}</span>
                  <select
                    className="prompt-remix-select"
                    value={String(imageGenerationOptions.image_count)}
                    onChange={event => updateImageGenerationOptions({ ...imageGenerationOptions, image_count: Number(event.target.value) })}
                    disabled={imageGenerationBusy}
                  >
                    {[1, 2, 3, 4].map(option => <option key={option} value={option}>{option}</option>)}
                  </select>
                </label>
              </div>
              {imageGenerationState.phase !== 'idle' && (
                <div className={`prompt-remix-image-status is-${imageGenerationStatusTone(imageGenerationState.phase)}`}>
                  <p>{imageGenerationStatusText}</p>
                  {imageGenerationState.phase === 'error' && (
                    <button type="button" className="secondary" onClick={handleGenerateImage}>
                      <RefreshCcw size={15} />
                      <span>{t('promptTemplateImageRetry')}</span>
                    </button>
                  )}
                </div>
              )}
            </section>
            <div className="prompt-remix-actions">
              <button type="button" className="primary" onClick={handleAssemble}>
                <Sparkles size={15} />
                <span>{t('promptTemplateAssemble')}</span>
              </button>
              <button type="button" className="primary" onClick={handleGenerateImage} disabled={imageGenerationBusy}>
                <Sparkles size={15} />
                <span>{imageGenerationButtonLabel}</span>
              </button>
              {assembledPreview && (
                <button type="button" className="secondary" onClick={handleCopyFinal}>
                  <Copy size={15} />
                  <span>{t('promptTemplateCopyFinal')}</span>
                </button>
              )}
            </div>
          </section>

          {assembledPreview && (
            <>
              <label className="prompt-remix-label">{t('promptTemplateFinalPrompt')}</label>
              <div className="prompt-remix-preview prompt-remix-preview-final">
                {assembledPreview.segments.map((segment, index) => renderPreviewSegment(segment, `assembled-${index}`))}
              </div>
            </>
          )}

          <label className="prompt-remix-label">{t('promptTemplateMarkedPrompt')}</label>
          <pre className="prompt-remix-marked-text">{template.marked_text}</pre>
      </>
    </section>
  );
}

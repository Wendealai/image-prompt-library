import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Copy, RefreshCcw, Sparkles, Wand2 } from 'lucide-react';
import { api } from '../api/client';
import { copyTextToClipboard } from '../utils/clipboard';
import { buildSlotValueRecord, renderMarkedPrompt } from '../utils/promptTemplate';
import type { PromptGenerationSessionRecord, PromptGenerationVariantRecord, PromptRenderSegment, PromptTemplateBundle } from '../types';
import type { Translator } from '../utils/i18n';

type LocalPromptPreview = {
  renderedText: string;
  segments: PromptRenderSegment[];
};

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
}: {
  itemId: string;
  t: Translator;
  onCopyResult: (success: boolean) => void;
}) {
  const [bundle, setBundle] = useState<PromptTemplateBundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [themeKeyword, setThemeKeyword] = useState('');
  const [feedback, setFeedback] = useState<{ tone: 'error' | 'success'; message: string } | null>(null);
  const [initializing, setInitializing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [rerolling, setRerolling] = useState(false);
  const [editorValues, setEditorValues] = useState<Record<string, string>>({});
  const [draftBaseValues, setDraftBaseValues] = useState<Record<string, string>>({});
  const [editingVariantId, setEditingVariantId] = useState('original');
  const [assembledPreview, setAssembledPreview] = useState<LocalPromptPreview | null>(null);
  const [targetedSlotId, setTargetedSlotId] = useState<string | null>(null);
  const slotInputRefs = useRef<Record<string, HTMLTextAreaElement | null>>({});
  const targetedSlotTimerRef = useRef<number | null>(null);

  const loadBundle = useCallback(async () => {
    setLoading(true);
    try {
      const nextBundle = await api.promptTemplate(itemId);
      setBundle(nextBundle);
      setFeedback(null);
    } catch (error) {
      setFeedback({ tone: 'error', message: extractErrorDetail(error) || t('promptTemplateUnavailable') });
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
    };
  }, []);

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

  const handleInit = async () => {
    setInitializing(true);
    setFeedback(null);
    try {
      const nextBundle = await api.initPromptTemplate(itemId);
      setBundle(nextBundle);
      setFeedback({ tone: 'success', message: `${t('promptTemplateReady')} · ${nextBundle.template?.slots.length || 0} ${t('promptTemplateSlots')}` });
    } catch (error) {
      setFeedback({ tone: 'error', message: extractErrorDetail(error) || t('promptTemplateUnavailable') });
    } finally {
      setInitializing(false);
    }
  };

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
  };

  const handleResetSlot = (slotId: string) => {
    const slot = slotLookup.get(slotId);
    if (!slot) return;
    setEditorValues(current => ({ ...current, [slotId]: slot.original_text }));
    setAssembledPreview(null);
  };

  const handleAssemble = () => {
    if (!livePreview) return;
    setAssembledPreview(livePreview);
  };

  const handleCopyFinal = async () => {
    const nextPreview = assembledPreview || livePreview;
    if (!nextPreview) return;
    if (!assembledPreview) setAssembledPreview(nextPreview);
    const copied = await copyTextToClipboard(nextPreview.renderedText);
    onCopyResult(copied);
    if (!copied) setFeedback({ tone: 'error', message: t('copyFailed') });
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

  return (
    <section className="prompt-remix-panel" aria-label={t('aiRewrite')}>
      <header className="prompt-remix-header">
        <div>
          <h3>{t('aiRewrite')}</h3>
          <p>{t('aiRewriteHelp')}</p>
        </div>
        <button type="button" className="secondary prompt-remix-init" onClick={handleInit} disabled={initializing}>
          <Wand2 size={15} />
          <span>{initializing ? t('promptTemplateInitializing') : template ? t('promptTemplateReinit') : t('promptTemplateInit')}</span>
        </button>
      </header>

      {feedback && <p className={`prompt-remix-feedback ${feedback.tone}`}>{feedback.message}</p>}

      {loading ? (
        <p className="prompt-remix-empty">{t('loading')}</p>
      ) : !template ? (
        <p className="prompt-remix-empty">{t('promptTemplateNoTemplate')}</p>
      ) : (
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
            <div className="prompt-remix-actions">
              <button type="button" className="primary" onClick={handleAssemble}>
                <Wand2 size={15} />
                <span>{t('promptTemplateAssemble')}</span>
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
      )}
    </section>
  );
}

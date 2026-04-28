import { useCallback, useEffect, useMemo, useState } from 'react';
import { Copy, RefreshCcw, Sparkles, Wand2 } from 'lucide-react';
import { api } from '../api/client';
import { copyTextToClipboard } from '../utils/clipboard';
import type { PromptGenerationSessionRecord, PromptGenerationVariantRecord, PromptTemplateBundle } from '../types';
import type { Translator } from '../utils/i18n';

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
  const [acceptingId, setAcceptingId] = useState('');

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
  const changedSlotLabels = useMemo(() => {
    const latestVariant = currentVariants[0];
    if (!latestVariant) return [];
    return latestVariant.segments
      .filter(segment => segment.type === 'slot' && segment.changed)
      .map(segment => segment.label || segment.slot_id || 'slot');
  }, [currentVariants]);

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
    } catch (error) {
      setFeedback({ tone: 'error', message: extractErrorDetail(error) || t('promptTemplateUnavailable') });
    } finally {
      setRerolling(false);
    }
  };

  const handleAcceptAndCopy = async (variant: PromptGenerationVariantRecord) => {
    setAcceptingId(variant.id);
    setFeedback(null);
    try {
      const session = await api.acceptPromptVariant(variant.id);
      setBundle(current => replaceSession(current, session));
      const copied = await copyTextToClipboard(variant.rendered_text);
      onCopyResult(copied);
      if (!copied) setFeedback({ tone: 'error', message: t('copyFailed') });
    } catch (error) {
      setFeedback({ tone: 'error', message: extractErrorDetail(error) || t('copyFailed') });
    } finally {
      setAcceptingId('');
    }
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

          <label className="prompt-remix-label">{t('promptTemplateMarkedPrompt')}</label>
          <pre className="prompt-remix-marked-text">{template.marked_text}</pre>

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
                const accepted = variant.accepted || currentSession.accepted_variant_id === variant.id;
                return (
                  <article key={variant.id} className={`prompt-remix-variant ${accepted ? 'is-accepted' : ''}`}>
                    <div className="prompt-remix-variant-head">
                      <strong>v{variant.iteration}</strong>
                      {accepted && <span className="prompt-remix-status is-accepted">{t('promptTemplateAccepted')}</span>}
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
                      <button type="button" className="secondary" onClick={() => handleAcceptAndCopy(variant)} disabled={acceptingId === variant.id}>
                        <Copy size={15} />
                        <span>{acceptingId === variant.id ? t('saving') : t('promptTemplateAcceptAndCopy')}</span>
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <p className="prompt-remix-empty">{t('promptTemplateNoVariants')}</p>
          )}
        </>
      )}
    </section>
  );
}

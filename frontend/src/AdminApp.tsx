import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { ArrowLeft, CheckCircle2, LockKeyhole, LogOut, RefreshCw, Sparkles, XCircle } from 'lucide-react';
import { ApiError, api } from './api/client';
import type {
  PromptTemplateBatchInitResponse,
  PromptTemplateBundle,
  PromptTemplateOpsItem,
  PromptTemplateOpsItemList,
  PromptTemplateRecord,
  PromptWorkflowFailureList,
  PromptWorkflowFailureRecord,
} from './types';
import { DEFAULT_UI_LANGUAGE, makeTranslator, normalizeUiLanguage, UI_LANGUAGE_LABELS, type UiLanguage } from './utils/i18n';

const UI_LANGUAGE_STORAGE_KEY = 'image-prompt-library.ui_language';
const APP_HOME_PATH = import.meta.env.BASE_URL || '/';
const UI_LANGUAGE_OPTIONS: UiLanguage[] = ['zh_hant', 'zh_hans', 'en'];
const TEMPLATE_OPS_LIMIT = 220;
const BATCH_VISIBLE_LIMIT = 24;
const FAILURE_LIMIT = 24;
const DATE_LOCALES: Record<UiLanguage, string> = {
  zh_hant: 'zh-Hant-TW',
  zh_hans: 'zh-CN',
  en: 'en-US',
};
const QUEUE_FILTERS = ['all', 'needs_init', 'pending_review', 'approved', 'rejected', 'failed'] as const;

type QueueFilter = typeof QUEUE_FILTERS[number];

function loadUiLanguage(): UiLanguage {
  if (typeof window === 'undefined') return DEFAULT_UI_LANGUAGE;
  return normalizeUiLanguage(window.localStorage.getItem(UI_LANGUAGE_STORAGE_KEY));
}

function summarizeError(error: unknown) {
  const rawMessage = error instanceof Error ? error.message : String(error);
  const compact = rawMessage.replace(/\s+/g, ' ').trim();
  if (!compact) return 'Unknown error';
  return compact.length > 240 ? `${compact.slice(0, 240)}…` : compact;
}

function formatTimestamp(value: string | undefined, uiLanguage: UiLanguage) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(DATE_LOCALES[uiLanguage], {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function reviewStatusLabel(reviewStatus: string, t: ReturnType<typeof makeTranslator>) {
  switch (reviewStatus) {
    case 'approved':
      return t('templateReviewApproved');
    case 'rejected':
      return t('templateReviewRejected');
    default:
      return t('templateReviewPending');
  }
}

function technicalStatusLabel(status: string, t: ReturnType<typeof makeTranslator>) {
  switch (status) {
    case 'missing':
      return t('templateOpsStatusMissing');
    case 'stale':
      return t('promptTemplateStale');
    case 'ready':
      return t('promptTemplateReady');
    case 'failed':
      return t('templateOpsStatusFailed');
    case 'no_prompt':
      return t('templateOpsStatusNoPrompt');
    default:
      return status;
  }
}

function queueLabel(queue: QueueFilter, t: ReturnType<typeof makeTranslator>) {
  switch (queue) {
    case 'needs_init':
      return t('templateQueueNeedsInit');
    case 'pending_review':
      return t('templateQueuePendingReview');
    case 'approved':
      return t('templateQueueApproved');
    case 'rejected':
      return t('templateQueueRejected');
    case 'failed':
      return t('templateQueueFailed');
    default:
      return t('templateOpsStatusAll');
  }
}

function itemMatchesQueue(item: PromptTemplateOpsItem, queue: QueueFilter) {
  if (queue === 'all') return true;
  if (queue === 'needs_init') return item.can_initialize || item.status === 'no_prompt';
  if (queue === 'pending_review') return item.status === 'ready' && item.review_status === 'pending_review';
  if (queue === 'approved') return item.status === 'ready' && item.review_status === 'approved';
  if (queue === 'rejected') return item.review_status === 'rejected';
  if (queue === 'failed') return item.status === 'failed';
  return true;
}

function queueCount(items: PromptTemplateOpsItem[], queue: QueueFilter) {
  return items.filter(item => itemMatchesQueue(item, queue)).length;
}

function batchCandidates(items: PromptTemplateOpsItem[]) {
  return items.filter(item => item.can_initialize).slice(0, BATCH_VISIBLE_LIMIT);
}

function isUnauthorized(error: unknown): error is ApiError {
  return error instanceof ApiError && error.status === 401;
}

export default function AdminApp() {
  const [uiLanguage, setUiLanguage] = useState<UiLanguage>(loadUiLanguage);
  const [authenticated, setAuthenticated] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [authLoading, setAuthLoading] = useState(false);
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authError, setAuthError] = useState<string>();
  const [password, setPassword] = useState('');
  const [opsData, setOpsData] = useState<PromptTemplateOpsItemList>();
  const [opsLoading, setOpsLoading] = useState(false);
  const [opsError, setOpsError] = useState<string>();
  const [queueFilter, setQueueFilter] = useState<QueueFilter>('pending_review');
  const [selectedItemId, setSelectedItemId] = useState<string>();
  const [selectedBundle, setSelectedBundle] = useState<PromptTemplateBundle>();
  const [selectedBundleLoading, setSelectedBundleLoading] = useState(false);
  const [selectedBundleError, setSelectedBundleError] = useState<string>();
  const [reviewNotes, setReviewNotes] = useState('');
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchResult, setBatchResult] = useState<PromptTemplateBatchInitResponse>();
  const [reviewLoading, setReviewLoading] = useState(false);
  const [failuresData, setFailuresData] = useState<PromptWorkflowFailureList>();
  const [failuresLoading, setFailuresLoading] = useState(false);
  const [selectedFailureId, setSelectedFailureId] = useState<string>();
  const [selectedFailure, setSelectedFailure] = useState<PromptWorkflowFailureRecord>();
  const [selectedFailureLoading, setSelectedFailureLoading] = useState(false);
  const [selectedFailureError, setSelectedFailureError] = useState<string>();
  const t = useMemo(() => makeTranslator(uiLanguage), [uiLanguage]);

  const clearAdminData = useCallback(() => {
    setOpsData(undefined);
    setOpsError(undefined);
    setSelectedItemId(undefined);
    setSelectedBundle(undefined);
    setSelectedBundleError(undefined);
    setReviewNotes('');
    setBatchResult(undefined);
    setFailuresData(undefined);
    setSelectedFailureId(undefined);
    setSelectedFailure(undefined);
    setSelectedFailureError(undefined);
  }, []);

  const handleUnauthorized = useCallback((error: unknown) => {
    if (!isUnauthorized(error)) return false;
    clearAdminData();
    setAuthenticated(false);
    setAuthChecked(true);
    setAuthError(t('adminSessionExpired'));
    setPassword('');
    return true;
  }, [clearAdminData, t]);

  const refreshSession = useCallback(async () => {
    setAuthLoading(true);
    setAuthError(undefined);
    try {
      const session = await api.adminSession();
      setAuthenticated(session.authenticated);
      if (!session.authenticated) clearAdminData();
    } catch (error) {
      setAuthenticated(false);
      clearAdminData();
      setAuthError(summarizeError(error));
    } finally {
      setAuthChecked(true);
      setAuthLoading(false);
    }
  }, [clearAdminData]);

  const refreshOps = useCallback(async () => {
    setOpsLoading(true);
    setOpsError(undefined);
    try {
      const nextOps = await api.adminPromptTemplateOpsItems({ limit: TEMPLATE_OPS_LIMIT });
      setOpsData(nextOps);
      setSelectedItemId(current => current && nextOps.items.some(item => item.item_id === current) ? current : nextOps.items[0]?.item_id);
    } catch (error) {
      if (handleUnauthorized(error)) return;
      setOpsError(summarizeError(error));
    } finally {
      setOpsLoading(false);
    }
  }, [handleUnauthorized]);

  const refreshFailures = useCallback(async () => {
    setFailuresLoading(true);
    try {
      const nextFailures = await api.adminPromptTemplateFailures(FAILURE_LIMIT);
      setFailuresData(nextFailures);
      setSelectedFailureId(current => current && nextFailures.failures.some(failure => failure.id === current) ? current : nextFailures.failures[0]?.id);
    } catch (error) {
      if (handleUnauthorized(error)) return;
      setFailuresData(undefined);
    } finally {
      setFailuresLoading(false);
    }
  }, [handleUnauthorized]);

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);

  useEffect(() => {
    if (!authenticated) return;
    void refreshOps();
    void refreshFailures();
  }, [authenticated, refreshFailures, refreshOps]);

  useEffect(() => {
    if (!authenticated) return;
    if (!selectedItemId) {
      setSelectedBundle(undefined);
      setReviewNotes('');
      return;
    }
    let cancelled = false;
    setSelectedBundleLoading(true);
    setSelectedBundleError(undefined);
    void api.adminPromptTemplate(selectedItemId)
      .then(bundle => {
        if (cancelled) return;
        setSelectedBundle(bundle);
        setReviewNotes(bundle.template?.review_notes || '');
      })
      .catch(error => {
        if (cancelled) return;
        if (handleUnauthorized(error)) return;
        setSelectedBundle(undefined);
        setReviewNotes('');
        setSelectedBundleError(summarizeError(error));
      })
      .finally(() => {
        if (!cancelled) setSelectedBundleLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [authenticated, handleUnauthorized, selectedItemId]);

  useEffect(() => {
    if (!authenticated) return;
    if (!selectedFailureId) {
      setSelectedFailure(undefined);
      setSelectedFailureError(undefined);
      return;
    }
    let cancelled = false;
    setSelectedFailureLoading(true);
    setSelectedFailureError(undefined);
    void api.adminPromptTemplateFailure(selectedFailureId)
      .then(failure => {
        if (!cancelled) setSelectedFailure(failure);
      })
      .catch(error => {
        if (cancelled) return;
        if (handleUnauthorized(error)) return;
        setSelectedFailure(undefined);
        setSelectedFailureError(summarizeError(error));
      })
      .finally(() => {
        if (!cancelled) setSelectedFailureLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [authenticated, handleUnauthorized, selectedFailureId]);

  const visibleItems = useMemo(() => {
    const items = opsData?.items || [];
    return items.filter(item => itemMatchesQueue(item, queueFilter));
  }, [opsData?.items, queueFilter]);

  const selectedItem = useMemo(
    () => visibleItems.find(item => item.item_id === selectedItemId) || opsData?.items.find(item => item.item_id === selectedItemId),
    [opsData?.items, selectedItemId, visibleItems],
  );
  const selectedTemplate = selectedBundle?.template;
  const visibleBatchCandidates = useMemo(() => batchCandidates(visibleItems), [visibleItems]);

  const updateUiLanguage = (language: UiLanguage) => {
    setUiLanguage(language);
    window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, language);
  };

  const refreshSelectedBundle = useCallback(async () => {
    if (!selectedItemId) return;
    setSelectedBundleLoading(true);
    setSelectedBundleError(undefined);
    try {
      const bundle = await api.adminPromptTemplate(selectedItemId);
      setSelectedBundle(bundle);
      setReviewNotes(bundle.template?.review_notes || '');
    } catch (error) {
      if (handleUnauthorized(error)) return;
      setSelectedBundle(undefined);
      setReviewNotes('');
      setSelectedBundleError(summarizeError(error));
    } finally {
      setSelectedBundleLoading(false);
    }
  }, [handleUnauthorized, selectedItemId]);

  const handleLogin = useCallback(async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!password.trim()) return;
    setAuthSubmitting(true);
    setAuthError(undefined);
    try {
      const session = await api.adminLogin(password.trim());
      setAuthenticated(session.authenticated);
      setAuthChecked(true);
      setPassword('');
    } catch (error) {
      setAuthError(summarizeError(error));
    } finally {
      setAuthSubmitting(false);
    }
  }, [password]);

  const handleLogout = useCallback(async () => {
    setAuthSubmitting(true);
    setAuthError(undefined);
    try {
      await api.adminLogout();
      clearAdminData();
      setAuthenticated(false);
      setPassword('');
    } catch (error) {
      setAuthError(summarizeError(error));
    } finally {
      setAuthSubmitting(false);
    }
  }, [clearAdminData]);

  const handleInitializeItem = useCallback(async (itemId: string) => {
    setReviewLoading(true);
    try {
      await api.adminInitPromptTemplate(itemId);
      await Promise.all([refreshOps(), refreshFailures(), selectedItemId === itemId ? refreshSelectedBundle() : Promise.resolve()]);
    } catch (error) {
      if (handleUnauthorized(error)) return;
      setSelectedBundleError(summarizeError(error));
    } finally {
      setReviewLoading(false);
    }
  }, [handleUnauthorized, refreshFailures, refreshOps, refreshSelectedBundle, selectedItemId]);

  const handleBatchInit = useCallback(async () => {
    if (!visibleBatchCandidates.length) return;
    setBatchLoading(true);
    setOpsError(undefined);
    try {
      const result = await api.adminBatchInitPromptTemplates({
        item_ids: visibleBatchCandidates.map(item => item.item_id),
        limit: visibleBatchCandidates.length,
      });
      setBatchResult(result);
      await Promise.all([refreshOps(), refreshFailures(), refreshSelectedBundle()]);
      const firstFailureId = result.results.find(item => item.failure_id)?.failure_id;
      if (firstFailureId) setSelectedFailureId(firstFailureId);
    } catch (error) {
      if (handleUnauthorized(error)) return;
      setOpsError(summarizeError(error));
    } finally {
      setBatchLoading(false);
    }
  }, [handleUnauthorized, refreshFailures, refreshOps, refreshSelectedBundle, visibleBatchCandidates]);

  const handleReview = useCallback(async (nextStatus: 'approved' | 'rejected') => {
    if (!selectedTemplate) return;
    setReviewLoading(true);
    setSelectedBundleError(undefined);
    try {
      const payload = { review_notes: reviewNotes.trim() || undefined };
      const reviewedTemplate: PromptTemplateRecord = nextStatus === 'approved'
        ? await api.adminApprovePromptTemplate(selectedTemplate.id, payload)
        : await api.adminRejectPromptTemplate(selectedTemplate.id, payload);
      setSelectedBundle(current => current ? { ...current, template: reviewedTemplate } : current);
      await refreshOps();
    } catch (error) {
      if (handleUnauthorized(error)) return;
      setSelectedBundleError(summarizeError(error));
    } finally {
      setReviewLoading(false);
    }
  }, [handleUnauthorized, refreshOps, reviewNotes, selectedTemplate]);

  if (!authenticated) {
    return (
      <div className="admin-shell admin-auth-shell">
        <header className="admin-header">
          <div>
            <div className="admin-eyebrow">AI Prompt Workflow</div>
            <h1>{t('adminPromptTemplates')}</h1>
            <p>{t('adminAuthHelp')}</p>
          </div>
          <div className="admin-header-actions">
            <div className="segmented-control admin-language-switcher" aria-label={t('uiLanguage')}>
              {UI_LANGUAGE_OPTIONS.map(language => (
                <button key={language} className={uiLanguage === language ? 'active' : ''} onClick={() => updateUiLanguage(language)}>
                  {UI_LANGUAGE_LABELS[language]}
                </button>
              ))}
            </div>
            <a className="secondary" href={APP_HOME_PATH}>
              <ArrowLeft size={14} />
              {t('adminReturnToLibrary')}
            </a>
          </div>
        </header>

        <main className="admin-main admin-auth-main">
          <section className="admin-auth-card">
            <div className="admin-auth-card-head">
              <LockKeyhole size={18} />
              <strong>{t('adminAuthTitle')}</strong>
            </div>
            <form className="admin-auth-form" onSubmit={handleLogin}>
              <label className="prompt-remix-label" htmlFor="admin-password">{t('adminPasswordLabel')}</label>
              <input
                id="admin-password"
                className="admin-auth-input"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={event => setPassword(event.currentTarget.value)}
                placeholder={t('adminPasswordPlaceholder')}
                disabled={authLoading || authSubmitting}
              />
              {authError ? <p className="config-inline-error">{authError}</p> : null}
              <button type="submit" className="primary" disabled={authLoading || authSubmitting || !password.trim()}>
                <LockKeyhole size={14} />
                {authLoading || authSubmitting || !authChecked ? t('adminLoggingIn') : t('adminLogin')}
              </button>
            </form>
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className="admin-shell">
      <header className="admin-header">
        <div>
          <div className="admin-eyebrow">AI Prompt Workflow</div>
          <h1>{t('adminPromptTemplates')}</h1>
          <p>{t('templateOpsHelp')}</p>
        </div>
        <div className="admin-header-actions">
          <div className="segmented-control admin-language-switcher" aria-label={t('uiLanguage')}>
            {UI_LANGUAGE_OPTIONS.map(language => (
              <button key={language} className={uiLanguage === language ? 'active' : ''} onClick={() => updateUiLanguage(language)}>
                {UI_LANGUAGE_LABELS[language]}
              </button>
            ))}
          </div>
          <button type="button" className="secondary" onClick={() => void handleLogout()} disabled={authSubmitting}>
            <LogOut size={14} />
            {t('adminLogout')}
          </button>
          <a className="secondary" href={APP_HOME_PATH}>
            <ArrowLeft size={14} />
            {t('adminReturnToLibrary')}
          </a>
        </div>
      </header>

      <main className="admin-main">
        <section className="admin-panel">
          <div className="config-section-head admin-panel-head">
            <div>
              <h2>{t('templateOpsCenter')}</h2>
              <p className="muted">{t('templateOpsScopeHelp')}</p>
            </div>
            <div className="config-inline-actions">
              <button type="button" className="secondary" onClick={() => void refreshOps()} disabled={opsLoading || batchLoading}>
                <RefreshCw size={14} />
                {t('templateOpsRefresh')}
              </button>
              <button type="button" className="primary" onClick={() => void handleBatchInit()} disabled={!visibleBatchCandidates.length || batchLoading}>
                <Sparkles size={14} />
                {batchLoading ? t('templateOpsRunning') : t('templateOpsRunVisible')}
              </button>
            </div>
          </div>

          <div className="segmented-control template-ops-statuses" aria-label={t('templateOpsCenter')}>
            {QUEUE_FILTERS.map(queue => (
              <button key={queue} className={queueFilter === queue ? 'active' : ''} onClick={() => setQueueFilter(queue)}>
                <span>{queueLabel(queue, t)}</span>
                <b>{queueCount(opsData?.items || [], queue)}</b>
              </button>
            ))}
          </div>

          {opsError ? <p className="config-inline-error">{opsError}</p> : null}

          <div className="admin-review-layout">
            <div className="template-ops-list" role="list">
              {visibleItems.length ? visibleItems.map(item => (
                <button
                  key={item.item_id}
                  type="button"
                  className={`template-ops-item admin-template-item ${selectedItemId === item.item_id ? 'active' : ''}`}
                  onClick={() => setSelectedItemId(item.item_id)}
                >
                  <div className="template-ops-item-head">
                    <div>
                      <strong>{item.title}</strong>
                      <p>{item.model}</p>
                    </div>
                    <span className={`prompt-remix-status ${item.published ? 'is-ready' : item.review_status === 'rejected' || item.status === 'failed' ? 'is-failed' : item.status === 'stale' || item.review_status === 'pending_review' ? 'is-stale' : ''}`}>{reviewStatusLabel(item.review_status, t)}</span>
                  </div>
                  <div className="template-ops-item-meta">
                    <span>{technicalStatusLabel(item.status, t)}</span>
                    <span>{item.slot_count} {t('promptTemplateSlots')}</span>
                    {item.prompt_updated_at ? <span>{formatTimestamp(item.prompt_updated_at, uiLanguage)}</span> : null}
                  </div>
                  <p className={`template-ops-item-text ${item.prompt_excerpt ? '' : 'is-empty'}`}>{item.prompt_excerpt || t('templateOpsPromptMissing')}</p>
                </button>
              )) : <p className="template-ops-empty">{opsLoading ? t('loading') : t('templateOpsNoItems')}</p>}
            </div>

            <div className="admin-template-review">
              <div className="template-failure-detail-head">
                <strong>{selectedItem?.title || t('templateReviewSelection')}</strong>
                {selectedTemplate ? <span>{selectedTemplate.id}</span> : null}
              </div>

              {selectedBundleLoading ? <p className="template-ops-empty">{t('loading')}</p> : null}
              {selectedBundleError ? <p className="config-inline-error">{selectedBundleError}</p> : null}
              {!selectedBundleLoading && !selectedItem ? <p className="template-ops-empty">{t('templateReviewSelection')}</p> : null}

              {selectedItem ? (
                <>
                  <div className="template-ops-toolbar-meta">
                    <span className={`prompt-remix-status ${selectedItem.published ? 'is-ready' : selectedItem.review_status === 'rejected' || selectedItem.status === 'failed' ? 'is-failed' : 'is-stale'}`}>{reviewStatusLabel(selectedItem.review_status, t)}</span>
                    <span className="template-ops-meta-pill">{technicalStatusLabel(selectedItem.status, t)}</span>
                    {selectedItem.published ? <span className="template-ops-meta-pill">{t('templateReviewPublished')}</span> : null}
                  </div>

                  <div className="config-inline-actions admin-review-actions">
                    <button type="button" className="secondary" onClick={() => selectedItem && void handleInitializeItem(selectedItem.item_id)} disabled={reviewLoading || !(selectedItem.can_initialize || Boolean(selectedTemplate))}>
                      <RefreshCw size={14} />
                      {selectedTemplate ? t('promptTemplateReinit') : t('promptTemplateInit')}
                    </button>
                    <button type="button" className="primary" onClick={() => void handleReview('approved')} disabled={reviewLoading || !(selectedTemplate && selectedTemplate.status === 'ready')}>
                      <CheckCircle2 size={14} />
                      {reviewLoading ? t('templateReviewReviewing') : t('templateReviewApprove')}
                    </button>
                    <button type="button" className="secondary" onClick={() => void handleReview('rejected')} disabled={reviewLoading || !(selectedTemplate && selectedTemplate.status === 'ready')}>
                      <XCircle size={14} />
                      {reviewLoading ? t('templateReviewReviewing') : t('templateReviewReject')}
                    </button>
                  </div>

                  <label className="prompt-remix-label" htmlFor="template-review-notes">{t('templateReviewNotes')}</label>
                  <textarea
                    id="template-review-notes"
                    className="admin-review-notes"
                    value={reviewNotes}
                    onChange={event => setReviewNotes(event.currentTarget.value)}
                    placeholder={t('templateReviewNotesPlaceholder')}
                  />

                  {selectedTemplate ? (
                    <div className="template-failure-detail-body">
                      <div className="template-failure-detail-section">
                        <strong>{t('templateReviewRawPrompt')}</strong>
                        <pre>{selectedTemplate.raw_text_snapshot}</pre>
                      </div>
                      <div className="template-failure-detail-section">
                        <strong>{t('promptTemplateMarkedPrompt')}</strong>
                        <pre>{selectedTemplate.marked_text}</pre>
                      </div>
                      <div className="template-failure-detail-section">
                        <strong>{t('promptTemplateSlots')}</strong>
                        <div className="prompt-remix-slot-list">
                          {selectedTemplate.slots.map(slot => (
                            <span key={slot.id} className="prompt-remix-slot-chip">{slot.label}</span>
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <p className="template-ops-empty">{t('promptTemplateNoTemplate')}</p>
                  )}
                </>
              ) : null}
            </div>
          </div>

          {batchResult ? (
            <div className="template-ops-batch-results">
              <div className="template-ops-batch-head">
                <strong>{t('templateOpsLastBatch')}</strong>
                <span>{t('templateOpsBatchSummary')}: {batchResult.initialized} / {batchResult.failed} / {batchResult.skipped}</span>
              </div>
              <div className="template-ops-batch-list">
                {batchResult.results.map(result => (
                  <div key={`${result.item_id}-${result.result}`} className="template-ops-batch-item">
                    <div className="template-ops-batch-item-head">
                      <strong>{result.title}</strong>
                      <span className={`prompt-remix-status ${result.result === 'initialized' ? 'is-ready' : result.result === 'failed' ? 'is-failed' : 'is-stale'}`}>{result.result}</span>
                    </div>
                    {result.detail ? <p>{result.detail}</p> : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </section>

        <section className="admin-panel">
          <div className="config-section-head admin-panel-head">
            <div>
              <h2>{t('templateOpsFailurePanel')}</h2>
              <p className="muted">{t('templateOpsFailurePanelHelp')}</p>
            </div>
            <button type="button" className="secondary" onClick={() => void refreshFailures()} disabled={failuresLoading}>
              <RefreshCw size={14} />
              {t('templateOpsRefresh')}
            </button>
          </div>

          <div className="template-failure-layout">
            <div className="template-failure-list">
              {failuresLoading && !(failuresData?.failures.length) ? <p className="template-ops-empty">{t('loading')}</p> : null}
              {(failuresData?.failures || []).map(failure => (
                <button key={failure.id} type="button" className={`template-failure-card ${selectedFailureId === failure.id ? 'active' : ''}`} onClick={() => setSelectedFailureId(failure.id)}>
                  <div className="template-failure-card-head">
                    <strong>{failure.error_class}</strong>
                    <span>{formatTimestamp(failure.created_at, uiLanguage)}</span>
                  </div>
                  <p>{failure.error_message}</p>
                  <div className="template-failure-card-meta">
                    <span>{failure.operation}</span>
                    {failure.item_id ? <span>{failure.item_id}</span> : null}
                    {typeof failure.response_status === 'number' ? <span>{failure.response_status}</span> : null}
                  </div>
                </button>
              ))}
              {!failuresLoading && !(failuresData?.failures.length) ? <p className="template-ops-empty">{t('templateOpsFailureEmpty')}</p> : null}
            </div>

            <div className="template-failure-detail">
              <div className="template-failure-detail-head">
                <strong>{t('templateOpsFailureDetail')}</strong>
                {selectedFailure ? <span>{selectedFailure.id}</span> : null}
              </div>
              {selectedFailureLoading ? <p className="template-ops-empty">{t('loading')}</p> : null}
              {selectedFailureError ? <p className="config-inline-error">{selectedFailureError}</p> : null}
              {!selectedFailureLoading && !selectedFailure && !selectedFailureError ? <p className="template-ops-empty">{t('templateOpsFailureSelect')}</p> : null}
              {selectedFailure ? (
                <div className="template-failure-detail-body">
                  <div className="template-failure-detail-section">
                    <strong>{t('templateOpsFailureContext')}</strong>
                    <pre>{JSON.stringify(selectedFailure.context, null, 2)}</pre>
                  </div>
                  {selectedFailure.workflow ? (
                    <div className="template-failure-detail-section">
                      <strong>{t('templateOpsFailureWorkflow')}</strong>
                      <pre>{JSON.stringify(selectedFailure.workflow, null, 2)}</pre>
                    </div>
                  ) : null}
                  {selectedFailure.traceback ? (
                    <div className="template-failure-detail-section">
                      <strong>{t('templateOpsFailureTraceback')}</strong>
                      <pre>{selectedFailure.traceback}</pre>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

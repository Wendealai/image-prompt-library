import { useEffect, useState } from 'react';
import { Sparkles, X } from 'lucide-react';
import { api, isDemoMode } from '../api/client';
import type { AppConfig, PromptTemplateBulkInitResult } from '../types';
import { UI_LANGUAGE_LABELS, type Translator, type UiLanguage } from '../utils/i18n';
import { PROMPT_LANGUAGE_LABELS, type PromptLanguage } from '../utils/prompts';

const LANGUAGE_OPTIONS: PromptLanguage[] = ['zh_hant', 'zh_hans', 'en'];
const UI_LANGUAGE_OPTIONS: UiLanguage[] = ['zh_hant', 'zh_hans', 'en'];
const GLOBAL_BUDGET_MIN = 50;
const GLOBAL_BUDGET_MAX = 150;
const GLOBAL_BUDGET_STEP = 5;
const FOCUS_BUDGET_MIN = 24;
const FOCUS_BUDGET_MAX = 100;
const FOCUS_BUDGET_STEP = 4;

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

export default function ConfigPanel({
  open,
  t,
  onClose,
  uiLanguage,
  onUiLanguage,
  preferredLanguage,
  onPreferredLanguage,
  globalThumbnailBudget,
  onGlobalThumbnailBudget,
  focusThumbnailBudget,
  onFocusThumbnailBudget,
}: {
  open: boolean;
  t: Translator;
  onClose: () => void;
  uiLanguage: UiLanguage;
  onUiLanguage: (language: UiLanguage) => void;
  preferredLanguage: PromptLanguage;
  onPreferredLanguage: (language: PromptLanguage) => void;
  globalThumbnailBudget: number;
  onGlobalThumbnailBudget: (budget: number) => void;
  focusThumbnailBudget: number;
  onFocusThumbnailBudget: (budget: number) => void;
}) {
  const [cfg, setCfg] = useState<AppConfig>();
  const [bulkRunning, setBulkRunning] = useState(false);
  const [bulkResult, setBulkResult] = useState<PromptTemplateBulkInitResult>();
  const [bulkError, setBulkError] = useState('');

  useEffect(() => {
    if (open) api.config().then(setCfg).catch(() => undefined);
  }, [open]);

  const runMissingPromptTemplates = async () => {
    setBulkRunning(true);
    setBulkError('');
    setBulkResult(undefined);
    try {
      const result = await api.bulkInitPromptTemplates({ mode: 'missing', limit: 500 });
      setBulkResult(result);
    } catch (error) {
      setBulkError(extractErrorDetail(error) || t('promptTemplateBulkUnavailable'));
    } finally {
      setBulkRunning(false);
    }
  };

  return (
    <aside className={`config drawer ${open ? 'open' : ''}`}>
      <div className="drawer-head">
        <h2>{t('config')}</h2>
        <button className="panel-close" onClick={onClose} aria-label={t('closeConfig')}><X size={18} /></button>
      </div>

      <section className="setting-group">
        <h3>{t('uiLanguage')}</h3>
        <div className="segmented-control" aria-label={t('uiLanguage')}>
          {UI_LANGUAGE_OPTIONS.map(language => (
            <button
              key={language}
              className={uiLanguage === language ? 'active' : ''}
              onClick={() => onUiLanguage(language)}
            >
              {UI_LANGUAGE_LABELS[language]}
            </button>
          ))}
        </div>
      </section>

      <section className="setting-group">
        <h3>{t('promptCopyLanguage')}</h3>
        <p className="muted">{t('promptCopyLanguageHelp')}</p>
        <div className="segmented-control" aria-label={t('preferredPromptLanguage')}>
          {LANGUAGE_OPTIONS.map(language => (
            <button
              key={language}
              className={preferredLanguage === language ? 'active' : ''}
              onClick={() => onPreferredLanguage(language)}
            >
              {PROMPT_LANGUAGE_LABELS[language]}
            </button>
          ))}
        </div>
      </section>

      <section className="setting-group range-setting">
        <div className="setting-title-row">
          <h3>{t('globalThumbnails')}</h3>
          <strong>{globalThumbnailBudget}</strong>
        </div>
        <p className="muted">{t('globalThumbnailsHelp')}</p>
        <input
          type="range"
          min={GLOBAL_BUDGET_MIN}
          max={GLOBAL_BUDGET_MAX}
          step={GLOBAL_BUDGET_STEP}
          value={globalThumbnailBudget}
          aria-label={t('globalThumbnailBudget')}
          onChange={event => onGlobalThumbnailBudget(Number(event.currentTarget.value))}
        />
        <div className="range-ticks"><span>{t('calm')}</span><span>{t('balanced')}</span><span>{t('dense')}</span></div>
      </section>

      <section className="setting-group range-setting">
        <div className="setting-title-row">
          <h3>{t('focusThumbnails')}</h3>
          <strong>{focusThumbnailBudget}</strong>
        </div>
        <p className="muted">{t('focusThumbnailsHelp')}</p>
        <input
          type="range"
          min={FOCUS_BUDGET_MIN}
          max={FOCUS_BUDGET_MAX}
          step={FOCUS_BUDGET_STEP}
          value={focusThumbnailBudget}
          aria-label={t('focusThumbnailBudget')}
          onChange={event => onFocusThumbnailBudget(Number(event.currentTarget.value))}
        />
        <div className="range-ticks"><span>{t('compact')}</span><span>{t('gallery')}</span><span>{t('full')}</span></div>
      </section>

      <section className="setting-group">
        <h3>{t('promptTemplateBulk')}</h3>
        <p className="muted">{t('promptTemplateBulkHelp')}</p>
        <button className="primary setting-action" onClick={runMissingPromptTemplates} disabled={bulkRunning || isDemoMode}>
          <Sparkles size={16} />
          <span>{bulkRunning ? t('promptTemplateBulkRunning') : t('promptTemplateBulkRunMissing')}</span>
        </button>
        {bulkResult && (
          <p className={`setting-feedback ${bulkResult.failed_count ? 'error' : 'success'}`}>
            {t('promptTemplateBulkResult')}: {bulkResult.processed_count}/{bulkResult.total_candidates}
            {bulkResult.failed_count ? ` · ${t('promptTemplateBulkFailed')}: ${bulkResult.failed_count}` : ''}
          </p>
        )}
        {bulkError && <p className="setting-feedback error">{bulkError}</p>}
      </section>

      <p>{t('libraryPath')}: <code>{cfg?.library_path}</code></p>
      <p>{t('databasePath')}: <code>{cfg?.database_path}</code></p>
    </aside>
  );
}

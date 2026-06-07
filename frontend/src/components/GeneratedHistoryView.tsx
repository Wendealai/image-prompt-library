import { Download, Eye, ExternalLink, Trash2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api, isDemoMode } from '../api/client';
import type { GeneratedImageHistoryEntry, GeneratedImageHistoryList } from '../types';
import { downloadBlobFromUrl } from '../utils/downloads';
import { imageDisplayPaths } from '../utils/images';
import type { Translator } from '../utils/i18n';
import FallbackImage from './FallbackImage';

const HISTORY_PAGE_SIZE = 120;

function formatHistoryDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date);
}

function imageDownloadUrl(entry: GeneratedImageHistoryEntry) {
  return `/api/items/${encodeURIComponent(entry.item_id)}/images/${encodeURIComponent(entry.image.id)}/download`;
}

function imageDownloadFilename(entry: GeneratedImageHistoryEntry) {
  const sourcePath = entry.image.original_path || entry.image.remote_url || entry.image.preview_path || entry.image.thumb_path || '';
  const extensionMatch = sourcePath.match(/\.([a-z0-9]+)(?:$|\?)/i);
  const extension = (extensionMatch?.[1] || 'jpg').toLowerCase().replace('jpeg', 'jpg');
  const safeTitle = entry.item_title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 72) || 'prompt-image';
  return `${safeTitle}-${entry.image.id}.${extension}`;
}

export default function GeneratedHistoryView({
  t,
  q,
  clusterId,
  useCase,
  reloadKey,
  onOpen,
  onChanged,
  showMutations = true,
}: {
  t: Translator;
  q: string;
  clusterId?: string;
  useCase?: string;
  reloadKey: number;
  onOpen: (itemId: string) => void;
  onChanged: () => void;
  showMutations?: boolean;
}) {
  const [history, setHistory] = useState<GeneratedImageHistoryList>({ items: [], total: 0, limit: HISTORY_PAGE_SIZE, offset: 0 });
  const [limit, setLimit] = useState(HISTORY_PAGE_SIZE);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const hasMore = history.items.length < history.total;

  useEffect(() => {
    setLimit(HISTORY_PAGE_SIZE);
  }, [q, clusterId, useCase, reloadKey]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(undefined);
    api.generatedImageHistory({ q, cluster: clusterId, use_case: useCase, limit, offset: 0 })
      .then(result => {
        if (!cancelled) setHistory(result);
      })
      .catch(nextError => {
        if (!cancelled) setError(String(nextError));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [q, clusterId, useCase, limit, reloadKey]);

  useEffect(() => {
    if (!hasMore || loading) return undefined;
    const sentinel = loadMoreRef.current;
    if (!sentinel) return undefined;
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        setLimit(current => current + HISTORY_PAGE_SIZE);
      }
    }, { rootMargin: '900px 0px' });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, loading]);

  const handleDownload = async (entry: GeneratedImageHistoryEntry, event?: { preventDefault?: () => void; stopPropagation?: () => void }) => {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    try {
      await downloadBlobFromUrl(imageDownloadUrl(entry), imageDownloadFilename(entry));
    } catch (nextError) {
      window.alert(nextError instanceof Error && nextError.message ? nextError.message : t('saveFailed'));
    }
  };

  const handleDelete = async (entry: GeneratedImageHistoryEntry, event?: { preventDefault?: () => void; stopPropagation?: () => void }) => {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    if (!showMutations || !window.confirm(t('deleteImageConfirm'))) return;
    try {
      await api.deleteImage(entry.item_id, entry.image.id);
      setHistory(current => ({
        ...current,
        items: current.items.filter(candidate => candidate.image.id !== entry.image.id),
        total: Math.max(0, current.total - 1),
      }));
      onChanged();
    } catch (nextError) {
      window.alert(nextError instanceof Error && nextError.message ? nextError.message : t('imageDeleteFailed'));
    }
  };

  if (loading && history.items.length === 0) {
    return <div className="loading">{t('loading')}</div>;
  }

  if (!loading && history.items.length === 0) {
    return (
      <section className="generated-library-view empty">
        <h2>{t('generatedImagesHistory')}</h2>
        <p>{t('generatedImagesEmpty')}</p>
      </section>
    );
  }

  return (
    <section className="generated-library-view" aria-label={t('generatedImagesHistory')}>
      <header className="generated-library-header">
        <div>
          <strong>{t('generatedImagesHistory')}</strong>
          <span>{history.total} {t('generatedImagesCount')}</span>
        </div>
        {error && <p className="generated-library-error">{error}</p>}
      </header>
      <div className="generated-library-grid">
        {history.items.map(entry => (
          <article className="generated-library-card" key={`${entry.item_id}-${entry.image.id}`}>
            <button type="button" className="generated-library-thumb" onClick={() => onOpen(entry.item_id)} aria-label={entry.item_title}>
              <FallbackImage paths={imageDisplayPaths(entry.image)} alt={entry.item_title} fallback={<span className="thumb-fallback">{t('noImage')}</span>} />
            </button>
            <div className="generated-library-meta">
              <strong>{entry.item_title}</strong>
              <span>{entry.source === 'workflow' ? t('promptTemplateImageRunSaved') : t('generatedImageDirectRun')}</span>
              <span>{formatHistoryDate(entry.created_at)}</span>
              {entry.run?.references.length ? <span>{t('promptTemplateImageRunReferences')}: {entry.run.references.length}</span> : null}
            </div>
            <div className="generated-library-actions">
              {entry.item_source_url && (
                <a className="modal-icon-button" href={entry.item_source_url} target="_blank" rel="noreferrer" aria-label={t('source')} title={t('source')}>
                  <ExternalLink size={15} />
                </a>
              )}
              <button type="button" className="modal-icon-button" onClick={() => onOpen(entry.item_id)} aria-label={entry.item_title} title={entry.item_title}>
                <Eye size={15} />
              </button>
              {!isDemoMode && (
                <button type="button" className="modal-icon-button" onClick={event => void handleDownload(entry, event)} aria-label={t('downloadImage')} title={t('downloadImage')}>
                  <Download size={15} />
                </button>
              )}
              {showMutations && (
                <button type="button" className="modal-icon-button is-danger" onClick={event => void handleDelete(entry, event)} aria-label={t('deleteImage')} title={t('deleteImage')}>
                  <Trash2 size={15} />
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
      <div className="cards-load-sentinel" ref={loadMoreRef} aria-hidden="true">
        {hasMore ? ' ' : null}
      </div>
    </section>
  );
}

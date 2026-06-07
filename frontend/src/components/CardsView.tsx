import { useEffect, useRef, useState } from 'react';
import type { ItemSummary } from '../types';
import type { Translator } from '../utils/i18n';
import ItemCard from './ItemCard';

export default function CardsView({
  items,
  duplicateGroupsByItemId,
  total,
  loadingMore = false,
  t,
  onOpen,
  onFavorite,
  onEdit,
  onCopyPrompt,
  onAdd,
  onLoadMore,
}: {
  items: ItemSummary[];
  duplicateGroupsByItemId?: Record<string, ItemSummary[]>;
  total: number;
  loadingMore?: boolean;
  t: Translator;
  onOpen: (id: string) => void;
  onFavorite?: (id: string) => void;
  onEdit?: (item: ItemSummary) => void;
  onCopyPrompt: (item: ItemSummary) => void;
  onAdd?: () => void;
  onLoadMore?: () => void;
}) {
  const [useMobileColumns, setUseMobileColumns] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 760px)').matches);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const showActions = Boolean(onFavorite && onEdit);
  const hasMore = items.length < total;

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const mediaQuery = window.matchMedia('(max-width: 760px)');
    const sync = () => setUseMobileColumns(mediaQuery.matches);
    sync();
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', sync);
      return () => mediaQuery.removeEventListener('change', sync);
    }
    mediaQuery.addListener(sync);
    return () => mediaQuery.removeListener(sync);
  }, []);

  useEffect(() => {
    if (!hasMore || !onLoadMore || loadingMore) return undefined;
    const sentinel = loadMoreRef.current;
    if (!sentinel) return undefined;
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) onLoadMore();
    }, { rootMargin: '900px 0px' });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, onLoadMore]);

  if (!items.length) {
    return (
      <div className="empty">
        <h2>{t('noMatchingPrompts')}</h2>
        <p>{t('noMatchingPromptsHelp')}</p>
        <div className="empty-actions">
          {onAdd && <button className="empty-primary" onClick={onAdd}>{t('addFirstPrompt')}</button>}
        </div>
      </div>
    );
  }

  const leftColumnItems = items.filter((_, index) => index % 2 === 0);
  const rightColumnItems = items.filter((_, index) => index % 2 === 1);
  const renderCard = (item: ItemSummary) => (
    <ItemCard key={item.id} t={t} item={item} duplicateCount={duplicateGroupsByItemId?.[item.id]?.length || 1} onOpen={onOpen} onFavorite={onFavorite} onEdit={onEdit} onCopyPrompt={onCopyPrompt} showActions={showActions} />
  );

  return (
    <>
      {useMobileColumns ? (
        <section className="mobile-masonry-columns">
          <div className="mobile-masonry-column">
            {leftColumnItems.map(renderCard)}
          </div>
          <div className="mobile-masonry-column">
            {rightColumnItems.map(renderCard)}
          </div>
        </section>
      ) : (
        <section className="cards-grid masonry-like desktop-cards-grid">
          {items.map(renderCard)}
        </section>
      )}
      <div className="cards-load-sentinel" ref={loadMoreRef} aria-hidden="true">
        {hasMore ? ' ' : null}
      </div>
    </>
  );
}

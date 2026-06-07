import { useMemo, useState } from 'react';
import { Search, SlidersHorizontal, X } from 'lucide-react';
import type { ClusterRecord, UseCaseRecord } from '../types';
import type { Translator } from '../utils/i18n';

export default function FiltersPanel({
  open,
  t,
  useCases,
  clusters,
  selectedUseCase,
  selectedCluster,
  onSelectUseCase,
  onSelect,
  onClear,
  onClose,
}: {
  open: boolean;
  t: Translator;
  useCases: UseCaseRecord[];
  clusters: ClusterRecord[];
  selectedUseCase?: string;
  selectedCluster?: string;
  onSelectUseCase: (name: string) => void;
  onSelect: (c: ClusterRecord) => void;
  onClear: () => void;
  onClose: () => void;
}) {
  const [collectionQuery, setCollectionQuery] = useState('');
  const total = clusters.reduce((sum, cluster) => sum + cluster.count, 0);
  const normalizedQuery = collectionQuery.trim().toLowerCase();
  const filteredUseCases = useMemo(
    () => normalizedQuery
      ? useCases.filter(useCase => useCase.name.toLowerCase().includes(normalizedQuery))
      : useCases,
    [useCases, normalizedQuery],
  );
  const filteredClusters = useMemo(
    () => normalizedQuery
      ? clusters.filter(cluster => cluster.name.toLowerCase().includes(normalizedQuery))
      : clusters,
    [clusters, normalizedQuery],
  );

  return (
    <aside className={`drawer filter-drawer ${open ? 'open' : ''}`} aria-label={t('filters')}>
      <div className="drawer-head filter-drawer-head">
        <div>
          <p className="drawer-eyebrow"><SlidersHorizontal size={15} /> {t('filters')}</p>
          <h2>{t('collections')}</h2>
        </div>
        <button className="panel-close" onClick={onClose} aria-label={t('closeFilters')}><X size={18} /></button>
      </div>

      <label className="filter-search">
        <Search size={17} />
        <input
          value={collectionQuery}
          onChange={event => setCollectionQuery(event.currentTarget.value)}
          placeholder={t('searchCollections')}
          aria-label={t('searchCollections')}
        />
      </label>

      <div className="filter-pill-grid" aria-label={t('collectionFilters')}>
        <button className={!selectedUseCase && !selectedCluster ? 'selected' : ''} onClick={onClear}>
          <span>{t('allReferences')}</span>
          <b>{total}</b>
        </button>
      </div>

      <section className="filter-section">
        <div className="filter-section-head">
          <strong>{t('useCases')}</strong>
        </div>
        <div className="filter-pill-grid" aria-label={t('useCaseFilters')}>
          <button className={!selectedUseCase ? 'selected' : ''} onClick={() => onSelectUseCase('')}>
            <span>{t('allUseCases')}</span>
            <b>{useCases.reduce((sum, useCase) => sum + useCase.count, 0)}</b>
          </button>
          {filteredUseCases.map(useCase => (
            <button key={useCase.name} className={selectedUseCase === useCase.name ? 'selected' : ''} onClick={() => onSelectUseCase(useCase.name)}>
              <span>{useCase.name}</span>
              <b>{useCase.count}</b>
            </button>
          ))}
        </div>
      </section>

      <section className="filter-section">
        <div className="filter-section-head">
          <strong>{t('collections')}</strong>
        </div>
        <div className="filter-pill-grid" aria-label={t('collectionFilters')}>
          {filteredClusters.map(cluster => (
            <button key={cluster.id} className={selectedCluster === cluster.id ? 'selected' : ''} onClick={() => onSelect(cluster)}>
              <span>{cluster.name}</span>
              <b>{cluster.count}</b>
            </button>
          ))}
        </div>
      </section>

      {filteredUseCases.length === 0 && filteredClusters.length === 0 && <div className="filter-empty">{t('noCollectionsFound')}</div>}
    </aside>
  );
}

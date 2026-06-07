import { useEffect, useMemo, useState } from 'react';
import { Check, Plus, XCircle } from 'lucide-react';
import { api, isDemoMode } from './api/client';
import TopBar from './components/TopBar';
import FiltersPanel from './components/FiltersPanel';
import ExploreView from './components/ExploreView';
import CardsView from './components/CardsView';
import GeneratedHistoryView from './components/GeneratedHistoryView';
import ItemDetailModal from './components/ItemDetailModal';
import ItemEditorModal from './components/ItemEditorModal';
import ConfigPanel from './components/ConfigPanel';
import { useDebouncedValue } from './hooks/useDebouncedValue';
import { useItemsQuery } from './hooks/useItemsQuery';
import type { CardsSortMode, ClusterRecord, ItemDetail, ItemSummary, TagRecord, UseCaseRecord, ViewMode } from './types';
import { copyTextToClipboard } from './utils/clipboard';
import { DEFAULT_UI_LANGUAGE, makeTranslator, normalizeUiLanguage, type UiLanguage } from './utils/i18n';
import { DEFAULT_PROMPT_LANGUAGE, normalizePromptLanguage, resolvePromptText, type PromptLanguage } from './utils/prompts';

const UI_LANGUAGE_STORAGE_KEY = 'image-prompt-library.ui_language';
const PROMPT_LANGUAGE_STORAGE_KEY = 'image-prompt-library.preferred_prompt_language';
const VIEW_STORAGE_KEY = 'image-prompt-library.view_mode.v2';
const CARDS_SORT_STORAGE_KEY = 'image-prompt-library.cards_sort_mode.v1';
const GLOBAL_THUMBNAIL_BUDGET_STORAGE_KEY = 'image-prompt-library.global_thumbnail_budget';
const FOCUS_THUMBNAIL_BUDGET_STORAGE_KEY = 'image-prompt-library.focus_thumbnail_budget';
const CARDS_QUERY_PAGE_SIZE = 120;

function loadPreferredLanguage(): PromptLanguage {
  if (typeof window === 'undefined') return DEFAULT_PROMPT_LANGUAGE;
  return normalizePromptLanguage(window.localStorage.getItem(PROMPT_LANGUAGE_STORAGE_KEY));
}

function loadUiLanguage(): UiLanguage {
  if (typeof window === 'undefined') return DEFAULT_UI_LANGUAGE;
  return normalizeUiLanguage(window.localStorage.getItem(UI_LANGUAGE_STORAGE_KEY));
}

function loadPreferredView(): ViewMode {
  if (typeof window === 'undefined') return 'explore';
  const savedView = window.localStorage.getItem(VIEW_STORAGE_KEY);
  if (savedView === 'explore' || savedView === 'cards' || savedView === 'history') return savedView;
  const isMobileViewport = window.matchMedia('(max-width: 760px)').matches;
  return isMobileViewport ? 'cards' : 'explore';
}

function loadCardsSortMode(): CardsSortMode {
  if (typeof window === 'undefined') return 'added';
  const savedSort = window.localStorage.getItem(CARDS_SORT_STORAGE_KEY);
  return savedSort === 'explore' || savedSort === 'added' ? savedSort : 'added';
}

function loadNumberSetting(key: string, fallback: number, min: number, max: number) {
  if (typeof window === 'undefined') return fallback;
  const raw = Number(window.localStorage.getItem(key));
  if (!Number.isFinite(raw)) return fallback;
  return Math.min(max, Math.max(min, Math.round(raw)));
}

function timeValue(value: string) {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function normalizedCardDuplicateKey(item: ItemSummary) {
  const sourceUrl = item.source_url?.trim().toLowerCase();
  if (sourceUrl) return `source:${sourceUrl}`;
  const firstImage = item.first_image;
  const imageKey = firstImage?.file_sha256 || firstImage?.remote_url || firstImage?.original_path || firstImage?.preview_path || firstImage?.thumb_path;
  if (imageKey) return `image:${String(imageKey).trim().toLowerCase()}`;
  return `item:${item.id}`;
}

export function buildCardDuplicateGroups(items: ItemSummary[]) {
  const groupsByKey = new Map<string, ItemSummary[]>();
  items.forEach(item => {
    const key = normalizedCardDuplicateKey(item);
    const current = groupsByKey.get(key);
    if (current) current.push(item);
    else groupsByKey.set(key, [item]);
  });
  const dedupedItems: ItemSummary[] = [];
  const groupsByItemId: Record<string, ItemSummary[]> = {};
  groupsByKey.forEach(group => {
    dedupedItems.push(group[0]);
    group.forEach(item => {
      groupsByItemId[item.id] = group;
    });
  });
  return { dedupedItems, groupsByItemId };
}

export function sortCardsItems(items: ItemSummary[], clusters: ClusterRecord[], cardsSortMode: CardsSortMode) {
  const addedOrder = (a: ItemSummary, b: ItemSummary) => timeValue(b.created_at) - timeValue(a.created_at) || a.title.localeCompare(b.title, 'zh-Hant');
  if (cardsSortMode === 'added') return [...items].sort(addedOrder);

  const clusterRank = new Map(
    [...clusters]
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'zh-Hant'))
      .map((cluster, index) => [cluster.id, index]),
  );
  return [...items].sort((a, b) => {
    const aRank = clusterRank.get(a.cluster?.id || '') ?? Number.MAX_SAFE_INTEGER;
    const bRank = clusterRank.get(b.cluster?.id || '') ?? Number.MAX_SAFE_INTEGER;
    return aRank - bRank || addedOrder(a, b);
  });
}

function buildExploreUseCaseClusters(items: ItemSummary[]) {
  const counts = new Map<string, number>();
  items.forEach(item => {
    const name = item.use_case?.trim() || '其他';
    counts.set(name, (counts.get(name) || 0) + 1);
  });
  return Array.from(counts.entries())
    .map(([name, count]) => ({ id: name, name, count, preview_images: [] as string[] }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'zh-Hant'));
}

function selectedCollectionNameSizeClass(name: string) {
  if (name.length > 28) return 'is-very-long';
  if (name.length > 16) return 'is-long';
  return '';
}

export default function App() {
  const [q, setQ] = useState('');
  const debouncedQ = useDebouncedValue(q);
  const [clusterId, setClusterId] = useState<string>();
  const [useCase, setUseCase] = useState<string>();
  const [view, setView] = useState<ViewMode>(loadPreferredView);
  const [cardsSortMode, setCardsSortMode] = useState<CardsSortMode>(loadCardsSortMode);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [clusters, setClusters] = useState<ClusterRecord[]>([]);
  const [tags, setTags] = useState<TagRecord[]>([]);
  const [useCases, setUseCases] = useState<UseCaseRecord[]>([]);
  const [detailId, setDetailId] = useState<string>();
  const [editing, setEditing] = useState<ItemDetail | undefined>();
  const [editorOpen, setEditorOpen] = useState(false);
  const [itemsReloadKey, setItemsReloadKey] = useState(0);
  const [uiLanguage, setUiLanguage] = useState<UiLanguage>(loadUiLanguage);
  const [preferredLanguage, setPreferredLanguage] = useState<PromptLanguage>(loadPreferredLanguage);
  const [globalThumbnailBudget, setGlobalThumbnailBudget] = useState(() => loadNumberSetting(GLOBAL_THUMBNAIL_BUDGET_STORAGE_KEY, 100, 50, 150));
  const [focusThumbnailBudget, setFocusThumbnailBudget] = useState(() => loadNumberSetting(FOCUS_THUMBNAIL_BUDGET_STORAGE_KEY, 100, 24, 100));
  const [cardsQueryLimit, setCardsQueryLimit] = useState(CARDS_QUERY_PAGE_SIZE);
  const [exploreFitRequestKey, setExploreFitRequestKey] = useState(0);
  const [pendingExploreUnfilterClusterId, setPendingExploreUnfilterClusterId] = useState<string>();
  const [exploreUnfilterFadePhase, setExploreUnfilterFadePhase] = useState<'out' | 'pre-in' | 'in' | 'idle'>('idle');
  const [toast, setToast] = useState<{ title: string; tone: 'success' | 'error' }>();
  const shouldExpandFilteredCards = view === 'cards' && Boolean(useCase);
  const itemQueryLimit = shouldExpandFilteredCards ? 5000 : view === 'cards' ? cardsQueryLimit : 5000;
  const { data, loading, initialLoading, refreshing, error, dataScope } = useItemsQuery(debouncedQ, clusterId, useCase, itemQueryLimit, itemsReloadKey, 'created_desc');
  const exploreClusters = useMemo(() => buildExploreUseCaseClusters(data.items), [data.items]);
  const exploreClusterById = useMemo(() => new Map(exploreClusters.map(cluster => [cluster.id, cluster])), [exploreClusters]);
  const exploreItems = useMemo(
    () => data.items.map(item => {
      const useCaseName = item.use_case?.trim() || '其他';
      const exploreCluster = exploreClusterById.get(useCaseName);
      return exploreCluster ? { ...item, cluster: exploreCluster } : item;
    }),
    [data.items, exploreClusterById],
  );
  const exploreFocusedClusterId = view === 'explore' ? useCase : clusterId;
  const selectedCluster = useMemo(() => clusters.find(c => c.id === clusterId), [clusters, clusterId]);
  const selectedUseCase = useMemo(() => useCases.find(record => record.name === useCase), [useCases, useCase]);
  const sortedCardItems = useMemo(() => sortCardsItems(data.items, clusters, cardsSortMode), [data.items, clusters, cardsSortMode]);
  const { dedupedItems: dedupedCardItems, groupsByItemId: cardDuplicateGroupsByItemId } = useMemo(() => buildCardDuplicateGroups(sortedCardItems), [sortedCardItems]);
  const activeCardDuplicateGroup = useMemo(() => (detailId ? cardDuplicateGroupsByItemId[detailId] : undefined), [detailId, cardDuplicateGroupsByItemId]);
  const t = useMemo(() => makeTranslator(uiLanguage), [uiLanguage]);
  const refreshClusters = () => api.clusters().then(setClusters).catch(() => setClusters([]));
  const refreshTags = () => api.tags().then(setTags).catch(() => setTags([]));
  const refreshUseCases = () => api.useCases().then(setUseCases).catch(() => setUseCases([]));
  useEffect(() => { refreshClusters(); refreshTags(); refreshUseCases(); }, []);
  useEffect(() => { setCardsQueryLimit(CARDS_QUERY_PAGE_SIZE); }, [debouncedQ, clusterId, useCase, itemsReloadKey]);
  useEffect(() => {
    if (pendingExploreUnfilterClusterId && dataScope.clusterId !== pendingExploreUnfilterClusterId) {
      setPendingExploreUnfilterClusterId(undefined);
      setExploreUnfilterFadePhase('pre-in');
      window.requestAnimationFrame(() => setExploreUnfilterFadePhase('in'));
      const timer = window.setTimeout(() => setExploreUnfilterFadePhase('idle'), 180);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [dataScope.clusterId, pendingExploreUnfilterClusterId]);
  const selectCluster = (c: ClusterRecord) => { setClusterId(c.id); updateView('cards'); setFiltersOpen(false); setPendingExploreUnfilterClusterId(undefined); setExploreUnfilterFadePhase('idle'); };
  const focusCluster = (c: ClusterRecord) => { setClusterId(undefined); setUseCase(c.id); updateView('explore'); setFiltersOpen(false); setPendingExploreUnfilterClusterId(undefined); setExploreUnfilterFadePhase('idle'); setExploreFitRequestKey(key => key + 1); };
  const handleFilterSelect = (c: ClusterRecord) => { selectCluster(c); };
  const clearCluster = () => {
    if (view === 'explore' && clusterId) {
      setPendingExploreUnfilterClusterId(clusterId);
      setExploreUnfilterFadePhase('out');
    }
    setClusterId(undefined);
  };
  const saved = () => { refreshClusters(); refreshTags(); refreshUseCases(); setItemsReloadKey(k => k + 1); };
  const deleted = () => { setDetailId(undefined); setEditing(undefined); refreshClusters(); refreshTags(); refreshUseCases(); setItemsReloadKey(k => k + 1); };
  const updatePreferredLanguage = (language: PromptLanguage) => {
    setPreferredLanguage(language);
    window.localStorage.setItem(PROMPT_LANGUAGE_STORAGE_KEY, language);
  };
  const updateUiLanguage = (language: UiLanguage) => {
    setUiLanguage(language);
    window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, language);
  };
  const updateView = (nextView: ViewMode) => {
    setView(nextView);
    window.localStorage.setItem(VIEW_STORAGE_KEY, nextView);
  };
  const updateCardsSortMode = (nextSortMode: CardsSortMode) => {
    setCardsSortMode(nextSortMode);
    window.localStorage.setItem(CARDS_SORT_STORAGE_KEY, nextSortMode);
  };
  const loadMoreCards = () => {
    if (view !== 'cards' || shouldExpandFilteredCards || loading || refreshing || data.items.length >= data.total) return;
    setCardsQueryLimit(limit => Math.min(data.total || limit + CARDS_QUERY_PAGE_SIZE, limit + CARDS_QUERY_PAGE_SIZE));
  };
  const updateGlobalThumbnailBudget = (budget: number) => {
    setGlobalThumbnailBudget(budget);
    window.localStorage.setItem(GLOBAL_THUMBNAIL_BUDGET_STORAGE_KEY, String(budget));
  };
  const updateFocusThumbnailBudget = (budget: number) => {
    setFocusThumbnailBudget(budget);
    window.localStorage.setItem(FOCUS_THUMBNAIL_BUDGET_STORAGE_KEY, String(budget));
  };
  const showCopyToast = (success: boolean) => {
    setToast({ title: success ? t('copySuccess') : t('copyFailed'), tone: success ? 'success' : 'error' });
    window.setTimeout(() => setToast(undefined), 1800);
  };
  const copyPrompt = async (item: ItemSummary) => {
    const text = resolvePromptText(item.prompts, preferredLanguage, item.title);
    const copied = await copyTextToClipboard(text);
    showCopyToast(copied);
  };
  const openNewItemEditor = () => { setEditing(undefined); setEditorOpen(true); };
  const favorite = (id: string) => { api.favorite(id).then(saved).catch(() => undefined); };
  const editSummary = (item: { id: string }) => { api.item(item.id).then(full => { setEditing(full); setEditorOpen(true); }).catch(() => undefined); };
  const showSelectedCollectionDock = Boolean(selectedCluster && !filtersOpen && !configOpen && !detailId && !editorOpen);
  return <div className={`app ${view === 'explore' ? 'explore-mode' : 'cards-mode'}`}>
    <TopBar t={t} q={q} onQ={setQ} view={view} onView={updateView} cardsSortMode={cardsSortMode} onCardsSortMode={updateCardsSortMode} onFilters={() => setFiltersOpen(true)} onConfig={() => setConfigOpen(true)} count={data.total} useCaseName={selectedUseCase?.name} clusterName={selectedCluster?.name} clearUseCase={() => setUseCase(undefined)} clearCluster={clearCluster} />
    {isDemoMode && (
      <div className="demo-banner" role="status">
        <strong>{t('onlineSandbox')}</strong>
        <span>{t('readOnlySampleLibrary')}</span>
        <span>{t('compressedForDemo')}</span>
        <span>{t('runLocallyForPrivateLibrary')}</span>
        <a href="https://github.com/EddieTYP/image-prompt-library" target="_blank" rel="noreferrer">{t('viewOnGitHub')}</a>
      </div>
    )}
    <FiltersPanel t={t} open={filtersOpen} useCases={useCases} clusters={clusters} selectedUseCase={useCase} selectedCluster={clusterId} onSelectUseCase={value => setUseCase(value || undefined)} onSelect={handleFilterSelect} onClear={() => { setUseCase(undefined); clearCluster(); }} onClose={() => setFiltersOpen(false)} />
    <ConfigPanel t={t} open={configOpen} onClose={() => setConfigOpen(false)} uiLanguage={uiLanguage} onUiLanguage={updateUiLanguage} preferredLanguage={preferredLanguage} onPreferredLanguage={updatePreferredLanguage} globalThumbnailBudget={globalThumbnailBudget} onGlobalThumbnailBudget={updateGlobalThumbnailBudget} focusThumbnailBudget={focusThumbnailBudget} onFocusThumbnailBudget={updateFocusThumbnailBudget} />
    {/* Static-test compatibility marker: <main className="app-main"> */}
    <main className={`app-main ${refreshing ? 'is-refreshing' : ''}`} aria-busy={refreshing}>
      {refreshing && <div className="refresh-indicator" role="status">{t('loading')}</div>}
      {initialLoading && <div className="loading">{t('loading')}</div>}
      {error && <div className="error">{error}</div>}
      {view === 'explore'
        ? <ExploreView t={t} clusters={exploreClusters} items={exploreItems} focusedClusterId={exploreFocusedClusterId} fitRequestKey={exploreFitRequestKey} unfilterTransitionPhase={exploreUnfilterFadePhase} globalThumbnailBudget={globalThumbnailBudget} focusThumbnailBudget={focusThumbnailBudget} onFocusCluster={focusCluster} onOpen={setDetailId} onAdd={isDemoMode ? undefined : openNewItemEditor} />
        : view === 'cards'
          ? <CardsView t={t} items={dedupedCardItems} duplicateGroupsByItemId={cardDuplicateGroupsByItemId} total={data.total} loadingMore={loading || refreshing} onLoadMore={loadMoreCards} onOpen={setDetailId} onFavorite={isDemoMode ? undefined : favorite} onEdit={isDemoMode ? undefined : editSummary} onCopyPrompt={copyPrompt} onAdd={isDemoMode ? undefined : openNewItemEditor} />
          : <GeneratedHistoryView t={t} q={debouncedQ} clusterId={clusterId} useCase={useCase} reloadKey={itemsReloadKey} onOpen={setDetailId} onChanged={saved} showMutations={!isDemoMode} />}
    </main>
    {showSelectedCollectionDock && selectedCluster && (
      <button className="selected-collection-dock" onClick={clearCluster} aria-label={`${t('collectionChip')}: ${selectedCluster.name}. ${t('close')}`}>
        <span className="selected-collection-dot" aria-hidden="true" />
        <span className={`selected-collection-name ${selectedCollectionNameSizeClass(selectedCluster.name)}`}>{selectedCluster.name}</span>
        <span className="selected-collection-count">{data.total} {t('referencesShown')}</span>
        <span className="selected-collection-clear" aria-hidden="true">×</span>
      </button>
    )}
    {!isDemoMode && <button className="fab" onClick={openNewItemEditor}><Plus/> {t('add')}</button>}
    <ItemDetailModal t={t} id={detailId} duplicateGroup={activeCardDuplicateGroup} onSelectDuplicateItem={setDetailId} preferredLanguage={preferredLanguage} clusters={clusters} tags={tags} onClose={() => setDetailId(undefined)} onCopyPrompt={showCopyToast} onChanged={saved} onEdit={(item) => { setDetailId(undefined); setEditing(item); setEditorOpen(true); }} showMutations={!isDemoMode} />
    {toast && <div className={`toast copy-toast elegant-toast ${toast.tone}`} role="status"><span className="toast-icon">{toast.tone === 'success' ? <Check size={16} /> : <XCircle size={16} />}</span><span className="toast-title">{toast.title}</span></div>}
    {editorOpen && <ItemEditorModal t={t} item={editing} clusters={clusters} tags={tags} onClose={() => setEditorOpen(false)} onSaved={saved} onDeleted={deleted} />}
  </div>
}

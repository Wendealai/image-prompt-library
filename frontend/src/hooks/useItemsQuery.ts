import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { ItemList, ItemSummary } from '../types';

const API_PAGE_LIMIT = 1000;

type QueryScope = {
  q: string;
  clusterId?: string;
  tag?: string;
  sort?: string;
  reloadKey: number;
};

function sameScope(left: QueryScope, right: QueryScope) {
  return left.q === right.q
    && left.clusterId === right.clusterId
    && left.tag === right.tag
    && left.sort === right.sort
    && left.reloadKey === right.reloadKey;
}

function dedupeItems(items: ItemSummary[]) {
  const seenIds = new Set<string>();
  return items.filter(item => {
    if (seenIds.has(item.id)) return false;
    seenIds.add(item.id);
    return true;
  });
}

async function fetchRange(q: string, clusterId: string | undefined, tag: string | undefined, sort: string | undefined, startOffset: number, targetCount: number) {
  const pages: ItemList[] = [];
  let remaining = targetCount;
  let offset = startOffset;
  while (remaining > 0) {
    const page = await api.items({
      q,
      cluster: clusterId,
      tag,
      sort,
      limit: Math.min(API_PAGE_LIMIT, remaining),
      offset,
    });
    pages.push(page);
    if (page.items.length === 0 || page.items.length < page.limit || offset + page.items.length >= page.total) break;
    remaining -= page.items.length;
    offset += page.items.length;
  }
  return pages;
}

export function useItemsQuery(q: string, clusterId?: string, tag?: string, viewLimit = 100, reloadKey = 0, sort?: string) {
  const [data, setData] = useState<ItemList>({ items: [], total: 0, limit: viewLimit, offset: 0 });
  const [dataScope, setDataScope] = useState<QueryScope>({ q: '', clusterId: undefined, tag: undefined, sort: undefined, reloadKey: 0 });
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => {
    let cancelled = false;
    const nextScope = { q, clusterId, tag, sort, reloadKey };
    const scopeChanged = !sameScope(dataScope, nextScope);
    const growingVisibleWindow = !scopeChanged && viewLimit > data.limit;
    const hasVisibleData = !scopeChanged && (data.items.length > 0 || data.total > 0);
    setLoading(true);
    setInitialLoading(!hasVisibleData);
    setRefreshing(hasVisibleData);
    setError(undefined);

    async function loadItems(): Promise<ItemList> {
      if (!scopeChanged && !growingVisibleWindow && data.limit === viewLimit) {
        return { ...data, limit: viewLimit };
      }

      if (!scopeChanged && growingVisibleWindow && data.items.length < data.total) {
        const desiredCount = Math.min(viewLimit, data.total);
        const pages = await fetchRange(q, clusterId, tag, sort, data.items.length, desiredCount - data.items.length);
        if (pages.length === 0) return { ...data, limit: viewLimit };
        const mergedItems = dedupeItems([...data.items, ...pages.flatMap(page => page.items)]).slice(0, desiredCount);
        const lastPage = pages[pages.length - 1];
        return { ...lastPage, items: mergedItems, limit: viewLimit, offset: 0 };
      }

      const pages = await fetchRange(q, clusterId, tag, sort, 0, viewLimit);
      const firstPage = pages[0] || { items: [], total: 0, limit: viewLimit, offset: 0 };
      const items = dedupeItems(pages.flatMap(page => page.items)).slice(0, viewLimit);
      return { ...firstPage, items, limit: viewLimit, offset: 0 };
    }

    loadItems()
      .then(nextData => {
        if (!cancelled) {
          setData(nextData);
          setDataScope(nextScope);
        }
      })
      .catch(e => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
          setInitialLoading(false);
          setRefreshing(false);
        }
      });

    return () => { cancelled = true; };
  }, [q, clusterId, tag, sort, viewLimit, reloadKey]);

  return { data, loading, initialLoading, refreshing, error, dataScope };
}

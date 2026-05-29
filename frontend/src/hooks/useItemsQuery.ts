import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { ItemList } from '../types';

const API_PAGE_LIMIT = 1000;

type QueryScope = {
  q: string;
  clusterId?: string;
  tag?: string;
  sort?: string;
  viewLimit: number;
};

export function useItemsQuery(q: string, clusterId?: string, tag?: string, viewLimit = 100, reloadKey = 0, sort?: string) {
  const [data, setData] = useState<ItemList>({ items: [], total: 0, limit: viewLimit, offset: 0 });
  const [dataScope, setDataScope] = useState<QueryScope>({ q: '', clusterId: undefined, tag: undefined, sort: undefined, viewLimit });
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => {
    let cancelled = false;
    const hasVisibleData = data.items.length > 0 || data.total > 0;
    setLoading(true);
    setInitialLoading(!hasVisibleData);
    setRefreshing(hasVisibleData);
    setError(undefined);

    async function loadItems(): Promise<ItemList> {
      const firstPageLimit = Math.min(viewLimit, API_PAGE_LIMIT);
      const firstPage = await api.items({ q, cluster: clusterId, tag, sort, limit: firstPageLimit, offset: 0 });
      if (firstPage.items.length >= viewLimit || firstPage.items.length >= firstPage.total) return firstPage;

      const nextOffsets: number[] = [];
      for (let offset = firstPage.items.length; offset < Math.min(firstPage.total, viewLimit); offset += API_PAGE_LIMIT) {
        nextOffsets.push(offset);
      }
      const nextPages = await Promise.all(nextOffsets.map(offset => api.items({ q, cluster: clusterId, tag, sort, limit: Math.min(API_PAGE_LIMIT, viewLimit - offset), offset })));
      const items = [...firstPage.items, ...nextPages.flatMap(page => page.items)].slice(0, viewLimit);
      return { ...firstPage, items, limit: viewLimit };
    }

    loadItems()
      .then(nextData => {
        if (!cancelled) {
          setData(nextData);
          setDataScope({ q, clusterId, tag, sort, viewLimit });
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

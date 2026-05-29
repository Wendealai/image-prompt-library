import { demoUrl, isDemoMode } from './demo';

export const mediaUrl = (path?: string) => {
  if (!path) return '';
  if (isDemoMode && path.startsWith('demo-data/')) return demoUrl(path);
  return `/media/${path}`;
};

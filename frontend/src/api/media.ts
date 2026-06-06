import { demoUrl, isDemoMode } from './demo';

export const mediaUrl = (path?: string) => {
  if (!path) return '';
  if (/^https?:\/\//i.test(path) || path.startsWith('data:image/')) return path;
  if (isDemoMode && path.startsWith('demo-data/')) return demoUrl(path);
  return `/media/${path}`;
};

import type { ImageRecord } from '../types';

function uniquePaths(paths: Array<string | undefined>) {
  return Array.from(new Set(paths.filter((path): path is string => Boolean(path))));
}

export function selectPrimaryImage(images: Array<ImageRecord | undefined>) {
  return images.find(image => image?.role === 'result_image') || images.find(Boolean);
}

export function imageDisplayPaths(image?: ImageRecord) {
  return uniquePaths([image?.preview_path, image?.original_path, image?.thumb_path]);
}

export function imageDisplayPath(image?: ImageRecord) {
  return image?.preview_path || image?.original_path || image?.thumb_path || '';
}

export function imageThumbnailPaths(image?: ImageRecord) {
  return uniquePaths([image?.thumb_path, image?.preview_path, image?.original_path]);
}

export function imageThumbnailPath(image?: ImageRecord) {
  return image?.thumb_path || image?.preview_path || '';
}

export function imageHeroPaths(image?: ImageRecord) {
  return uniquePaths([image?.preview_path, image?.original_path, image?.thumb_path]);
}

export function imageHeroPath(image?: ImageRecord) {
  return image?.preview_path || image?.original_path || image?.thumb_path || '';
}

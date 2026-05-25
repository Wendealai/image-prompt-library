import type { ImgHTMLAttributes, ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { mediaUrl } from '../api/client';

type FallbackImageProps = Omit<ImgHTMLAttributes<HTMLImageElement>, 'src'> & {
  paths: string[];
  fallback?: ReactNode;
};

export default function FallbackImage({ paths, fallback = null, onError, ...imgProps }: FallbackImageProps) {
  const imagePaths = useMemo(() => Array.from(new Set(paths.filter(Boolean))), [paths]);
  const imageKey = imagePaths.join('\n');
  const [pathIndex, setPathIndex] = useState(0);

  useEffect(() => {
    setPathIndex(0);
  }, [imageKey]);

  if (pathIndex >= imagePaths.length) return <>{fallback}</>;

  return (
    <img
      {...imgProps}
      src={mediaUrl(imagePaths[pathIndex])}
      onError={event => {
        onError?.(event);
        if (event.isDefaultPrevented()) return;
        setPathIndex(currentIndex => Math.min(currentIndex + 1, imagePaths.length));
      }}
    />
  );
}

import type { MouseEvent } from 'react';
import { Copy, Heart, Pencil } from 'lucide-react';
import FallbackImage from './FallbackImage';
import type { ItemSummary } from '../types';
import { imageDisplayPaths, selectPrimaryImage } from '../utils/images';
import type { Translator } from '../utils/i18n';

export default function ItemCard({
  item,
  t,
  onOpen,
  onFavorite,
  onEdit,
  onCopyPrompt,
  showActions = true,
}: {
  item: ItemSummary;
  t: Translator;
  onOpen: (id: string) => void;
  onFavorite?: (id: string) => void;
  onEdit?: (item: ItemSummary) => void;
  onCopyPrompt: (item: ItemSummary) => void;
  showActions?: boolean;
}) {
  const primaryImage = selectPrimaryImage([item.first_image]);
  const imagePaths = imageDisplayPaths(primaryImage);
  const imageAspectRatio = primaryImage?.width && primaryImage?.height
    ? `${primaryImage.width} / ${primaryImage.height}`
    : undefined;
  const copyPrompt = (event: MouseEvent) => {
    event.stopPropagation();
    onCopyPrompt(item);
  };
  const favorite = (event: MouseEvent) => {
    event.stopPropagation();
    onFavorite?.(item.id);
  };
  const edit = (event: MouseEvent) => {
    event.stopPropagation();
    onEdit?.(item);
  };

  return (
    <article className={`item-card ${item.favorite ? 'is-favorite' : ''}`} style={{ breakInside: 'avoid' }} onClick={() => onOpen(item.id)}>
      {imagePaths.length ? (
        <div className={`card-image-frame ${imageAspectRatio ? 'has-reserved-ratio' : 'natural-ratio'}`} style={{ aspectRatio: imageAspectRatio }}>
          <FallbackImage
            paths={imagePaths}
            loading="lazy"
            decoding="async"
            width={primaryImage?.width || undefined}
            height={primaryImage?.height || undefined}
            alt={item.title}
            fallback={<span className="placeholder image-load-fallback">{t('noImage')}</span>}
          />
        </div>
      ) : <div className="placeholder">{t('noImage')}</div>}
      <div className="card-body">
        <h3>{item.title}</h3>
      </div>
      <div className="card-actions" aria-label={t('itemActions')}>
        <button className="hover-action" onClick={copyPrompt}><Copy size={15} /> <span className="action-label">{t('copyPrompt')}</span></button>
        {showActions && onFavorite && <button className="hover-action" onClick={favorite}><Heart size={15} fill={item.favorite ? 'currentColor' : 'none'} /> <span className="action-label">{t('favorite')}</span></button>}
        {showActions && onEdit && <button className="hover-action" onClick={edit}><Pencil size={15} /> <span className="action-label">{t('edit')}</span></button>}
      </div>
    </article>
  );
}

import type { ReactNode } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import { revealMature, useRevealedMature } from './rating';

/** A cover thumbnail; a mature project's stays blurred until clicked (once per session).
    interactive=false (inside another button): blurred, no reveal button. */
export function MatureCover({ id, src, alt, mature, interactive = true, placeholder }: {
  id: string;
  src: string | null | undefined;
  alt: string;
  mature: boolean;
  interactive?: boolean;
  placeholder: ReactNode;
}) {
  const { t } = useTranslation();
  const revealed = useRevealedMature();
  if (!src) return <>{placeholder}</>;
  const hidden = mature && !revealed.has(id);
  return (
    <div className={`rated-cover${hidden ? ' rated-cover-hidden' : ''}`}>
      <img src={src} alt={alt} loading="lazy" />
      {hidden && (interactive ? (
        <button type="button" className="rated-cover-reveal"
          onClick={e => { e.stopPropagation(); revealMature(id); }}>
          {t.showcase.matureReveal}
        </button>
      ) : (
        <span className="rated-cover-reveal">{t.showcase.matureBadge}</span>
      ))}
    </div>
  );
}

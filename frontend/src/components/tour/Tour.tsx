import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useTranslation, fill } from '../../hooks/useTranslation';
import {
  ALL_TOURS, TOURS, markSeen, nextStep, placePopover, spotlightRect,
  type Rect, type TourTab,
} from './tourLogic';
import './tour.css';

const find = (target: string) =>
  document.querySelector<HTMLElement>(`[data-tour="${CSS.escape(target)}"]`);

const isShown = (target: string) => {
  const el = find(target);
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};

/** A spotlight tour of one tab. Steps whose element is not on the page (an
 *  empty list, a button that only shows in some states) are skipped. */
export function Tour({ tab, onClose }: { tab: TourTab; onClose: () => void }) {
  const { t } = useTranslation();
  const steps = TOURS[tab];
  const text = t.tour.steps[tab] as Record<string, { title: string; body: string }>;

  const [index, setIndex] = useState(0);
  const [spot, setSpot] = useState<Rect | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);

  const step = steps[index];
  const prev = nextStep(steps, index, -1, isShown);
  const next = nextStep(steps, index, 1, isShown);
  // count only the steps that will actually be shown
  const visible = steps.filter(s => !s.target || isShown(s.target));
  const position = visible.indexOf(step) + 1;

  const close = useCallback((all = false) => {
    markSeen(all ? ALL_TOURS : tab);
    onClose();
  }, [tab, onClose]);

  const measure = useCallback(() => {
    const vp = { width: window.innerWidth, height: window.innerHeight };
    const el = step.target ? find(step.target) : null;
    const r = el?.getBoundingClientRect();
    const s = r && r.width > 0 ? spotlightRect({ top: r.top, left: r.left, width: r.width, height: r.height }, vp) : null;
    setSpot(s);
    const pop = popRef.current;
    const size = pop ? { width: pop.offsetWidth, height: pop.offsetHeight } : { width: 340, height: 200 };
    setPos(placePopover(s, size, vp));
  }, [step]);

  // bring the target into view, then measure once the scroll has settled
  useLayoutEffect(() => {
    const el = step.target ? find(step.target) : null;
    el?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    const id = requestAnimationFrame(measure);
    return () => cancelAnimationFrame(id);
  }, [step, measure]);

  useEffect(() => {
    nextRef.current?.focus({ preventScroll: true });
  }, [index]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); close(); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); if (next >= 0) setIndex(next); else close(); }
      else if (e.key === 'ArrowLeft' && prev >= 0) { e.preventDefault(); setIndex(prev); }
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [close, measure, next, prev]);

  const words = text[step.key];

  return (
    <div className="tour-root">
      {/* blocks clicks on the page while the tour is open */}
      <div className={`tour-backdrop ${spot ? '' : 'is-dim'}`} onClick={e => e.stopPropagation()} />
      {spot && (
        <div className="tour-spot" style={{ top: spot.top, left: spot.left, width: spot.width, height: spot.height }} />
      )}
      <div
        ref={popRef}
        className="tour-pop"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
        aria-describedby="tour-body"
        style={pos ? { top: pos.top, left: pos.left } : { visibility: 'hidden' }}
      >
        <div className="tour-count">{fill(t.tour.stepOf, { n: position, total: visible.length })}</div>
        <h3 id="tour-title">{words.title}</h3>
        <p id="tour-body">{words.body}</p>
        <div className="tour-actions">
          <button type="button" className="btn btn-ghost tour-skip" onClick={() => close()}>
            {next >= 0 ? t.tour.skip : t.tour.close}
          </button>
          <div className="tour-actions-right">
            {prev >= 0 && (
              <button type="button" className="btn btn-secondary" onClick={() => setIndex(prev)}>{t.tour.back}</button>
            )}
            <button ref={nextRef} type="button" className="btn btn-primary"
              onClick={() => (next >= 0 ? setIndex(next) : close())}>
              {next >= 0 ? t.tour.next : t.tour.done}
            </button>
          </div>
        </div>
        {position === 1 && (
          <button type="button" className="tour-off" onClick={() => close(true)}>{t.tour.turnOff}</button>
        )}
      </div>
    </div>
  );
}

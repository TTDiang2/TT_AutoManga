import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { placeTip, withId } from './tooltipLogic';
import './tooltip.css';

const ID = 'am-tooltip';
const HOVER_DELAY = 450;

/** One tooltip for the whole app: any element with `data-tip="…"` gets it on
 *  hover (after a short delay) or keyboard focus. Mount once, in App. */
export function TooltipLayer() {
  const [shown, setShown] = useState<{ text: string; el: HTMLElement } | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const tipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let timer = 0;
    let pending: HTMLElement | null = null;
    let current: HTMLElement | null = null;
    let lastPointer = 0;

    const tipOf = (t: EventTarget | null) =>
      t instanceof Element ? t.closest<HTMLElement>('[data-tip]') : null;

    const hide = () => {
      window.clearTimeout(timer);
      pending = null;
      if (current) {
        const ids = withId(current.getAttribute('aria-describedby'), ID, false);
        if (ids) current.setAttribute('aria-describedby', ids); else current.removeAttribute('aria-describedby');
      }
      current = null;
      setShown(null);
      setPos(null);
    };

    const show = (el: HTMLElement, delay: number) => {
      if (el === current || el === pending) return;
      hide();
      pending = el;
      timer = window.setTimeout(() => {
        pending = null;
        const text = el.dataset.tip?.trim();
        if (!text || !el.isConnected) return;
        current = el;
        el.setAttribute('aria-describedby', withId(el.getAttribute('aria-describedby'), ID, true));
        setShown({ text, el });
      }, delay);
    };

    const onOver = (e: PointerEvent) => {
      if (e.pointerType === 'touch') return;   // no hover on touch screens
      const el = tipOf(e.target);
      if (el) show(el, HOVER_DELAY);
    };
    const onOut = (e: PointerEvent) => {
      const from = pending || current;
      if (from && !(e.relatedTarget instanceof Node && from.contains(e.relatedTarget))) hide();
    };
    const onFocus = (e: FocusEvent) => {
      // keyboard focus only: a click focuses too (text fields even count as
      // :focus-visible then), and should not pop a tip over what you clicked
      if (Date.now() - lastPointer < 300) return;
      const el = tipOf(e.target);
      if (el) show(el, 0);
    };
    const onDown = () => { lastPointer = Date.now(); hide(); };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') hide(); };

    document.addEventListener('pointerover', onOver);
    document.addEventListener('pointerout', onOut);
    document.addEventListener('focusin', onFocus);
    document.addEventListener('focusout', hide);
    document.addEventListener('pointerdown', onDown, true);
    document.addEventListener('keydown', onKey);
    document.addEventListener('input', hide, true);   // typing: get out of the way
    window.addEventListener('scroll', hide, true);
    window.addEventListener('resize', hide);
    return () => {
      hide();
      document.removeEventListener('pointerover', onOver);
      document.removeEventListener('pointerout', onOut);
      document.removeEventListener('focusin', onFocus);
      document.removeEventListener('focusout', hide);
      document.removeEventListener('pointerdown', onDown, true);
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('input', hide, true);
      window.removeEventListener('scroll', hide, true);
      window.removeEventListener('resize', hide);
    };
  }, []);

  // place it once its size is known
  useLayoutEffect(() => {
    if (!shown || !tipRef.current) return;
    const r = shown.el.getBoundingClientRect();
    const tip = tipRef.current;
    setPos(placeTip(
      { top: r.top, left: r.left, width: r.width, height: r.height },
      { width: tip.offsetWidth, height: tip.offsetHeight },
      { width: window.innerWidth, height: window.innerHeight },
    ));
  }, [shown]);

  if (!shown) return null;
  // a modal <dialog> sits in the browser's top layer, above anything in
  // <body>: render the tip inside it, or it would be hidden behind the dialog
  const host = shown.el.closest<HTMLElement>('dialog[open]') ?? document.body;
  return createPortal(
    <div
      ref={tipRef}
      id={ID}
      role="tooltip"
      className="am-tip"
      style={pos ? { top: pos.top, left: pos.left } : { top: 0, left: 0, visibility: 'hidden' }}
    >
      {shown.text}
    </div>,
    host,
  );
}

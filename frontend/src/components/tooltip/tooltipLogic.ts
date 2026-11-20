export interface Box { top: number; left: number; width: number; height: number }
export interface Size { width: number; height: number }

const GAP = 8;
const MARGIN = 8;

/** Above the element, centred; below when there is no room above. Always
 *  kept inside the viewport horizontally. */
export function placeTip(target: Box, tip: Size, vp: Size): { top: number; left: number; side: 'top' | 'bottom' } {
  const left = Math.max(MARGIN, Math.min(vp.width - tip.width - MARGIN, target.left + target.width / 2 - tip.width / 2));
  const above = target.top - GAP - tip.height;
  if (above >= MARGIN) return { top: above, left, side: 'top' };
  const below = target.top + target.height + GAP;
  return { top: Math.min(below, Math.max(MARGIN, vp.height - tip.height - MARGIN)), left, side: 'bottom' };
}

/** Adds or removes one id in a space-separated aria-describedby list. */
export function withId(list: string | null, id: string, on: boolean): string {
  const ids = (list || '').split(/\s+/).filter(x => x && x !== id);
  if (on) ids.push(id);
  return ids.join(' ');
}

/** Every leaf of a tips object as "path.to.key" → text, for checks. */
export function flattenTips(obj: unknown, prefix = ''): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (obj && typeof obj === 'object') {
    for (const [k, v] of Object.entries(obj)) {
      const key = prefix ? `${prefix}.${k}` : k;
      if (v && typeof v === 'object') Object.assign(out, flattenTips(v, key));
      else out[key] = v;
    }
  }
  return out;
}

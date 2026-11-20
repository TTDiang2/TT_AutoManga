import type { TabId } from '../../types';

/** One stop of a tab's tour. `target` names a `data-tour="…"` element; a step
 *  without one is shown centred (intros). Text lives in i18n `tour.steps`. */
export interface TourStep {
  key: string;
  target?: string;
}

export type TourTab = TabId;

export const TOURS: Record<TourTab, TourStep[]> = {
  // the landing tab: doubles as the app's welcome for new users
  wizard: [
    { key: 'intro' },
    { key: 'steps', target: 'wizard-steps' },
    { key: 'card', target: 'wizard-card' },
    { key: 'tip', target: 'wizard-tip' },
    { key: 'nav', target: 'wizard-nav' },
    { key: 'project', target: 'wizard-project' },
    { key: 'tabs', target: 'app-tabs' },
  ],
  storyboard: [
    { key: 'intro' },
    { key: 'input', target: 'storyboard-input' },
    { key: 'detail', target: 'storyboard-detail' },
    { key: 'generate', target: 'storyboard-generate' },
    { key: 'panels', target: 'storyboard-panels' },
  ],
  characters: [
    { key: 'intro' },
    { key: 'new', target: 'characters-new' },
    { key: 'templates', target: 'characters-templates' },
    { key: 'list', target: 'characters-list' },
    { key: 'detail', target: 'characters-detail' },
  ],
  prompt: [
    { key: 'intro' },
    { key: 'mode', target: 'prompt-mode' },
    { key: 'generateAll', target: 'prompt-generate-all' },
    { key: 'panel', target: 'prompt-panel' },
    { key: 'workspace', target: 'prompt-workspace' },
    { key: 'overview', target: 'prompt-overview' },
  ],
  assets: [
    { key: 'intro' },
    { key: 'status', target: 'assets-status' },
    { key: 'mode', target: 'assets-mode' },
    { key: 'view', target: 'assets-view' },
    { key: 'generateAll', target: 'assets-generate-all' },
    { key: 'grid', target: 'assets-grid' },
  ],
  composer: [
    { key: 'intro' },
    { key: 'pages', target: 'composer-pages' },
    { key: 'tools', target: 'composer-tools' },
    { key: 'templates', target: 'composer-templates' },
    { key: 'properties', target: 'composer-properties' },
    { key: 'save', target: 'composer-save' },
  ],
  showcase: [
    { key: 'intro' },
    { key: 'view', target: 'showcase-view' },
    { key: 'new', target: 'showcase-new' },
    { key: 'grid', target: 'showcase-grid' },
  ],
  comics: [
    { key: 'intro' },
    { key: 'list', target: 'comics-list' },
    { key: 'main', target: 'comics-main' },
  ],
  settings: [
    { key: 'intro' },
    { key: 'api', target: 'settings-api' },
    { key: 'swarmui', target: 'settings-swarmui' },
    { key: 'defaults', target: 'settings-defaults' },
    { key: 'save', target: 'settings-save' },
  ],
};

export function hasTour(tab: TabId): tab is TourTab {
  return tab in TOURS;
}

/** The next step index in `dir` whose target is on the page (steps without a
 *  target always count), or -1 when there is none. */
export function nextStep(steps: TourStep[], from: number, dir: 1 | -1, present: (target: string) => boolean): number {
  for (let i = from + dir; i >= 0 && i < steps.length; i += dir) {
    const t = steps[i].target;
    if (!t || present(t)) return i;
  }
  return -1;
}

// --- which tours the viewer has already seen ---------------------------------

const SEEN_KEY = 'automanga-tours-seen';
export const ALL_TOURS = '*';

export function parseSeen(raw: string | null): Set<string> {
  try {
    const v = JSON.parse(raw || '[]');
    return new Set(Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []);
  } catch {
    return new Set();
  }
}

function readSeen(): Set<string> {
  try { return parseSeen(localStorage.getItem(SEEN_KEY)); } catch { return new Set(); }
}

export function isSeen(tab: string): boolean {
  const seen = readSeen();
  return seen.has(ALL_TOURS) || seen.has(tab);
}

export function markSeen(tab: string) {
  const seen = readSeen();
  seen.add(tab);
  try { localStorage.setItem(SEEN_KEY, JSON.stringify([...seen])); } catch { /* storage blocked: the tour just shows again */ }
}

// --- geometry ------------------------------------------------------------------

export interface Rect { top: number; left: number; width: number; height: number }
export interface Size { width: number; height: number }
export type Placement = 'bottom' | 'top' | 'right' | 'left' | 'over' | 'center';

const GAP = 12;     // between the spotlight and the popover
const MARGIN = 12;  // keep the popover this far inside the viewport

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

/** The highlighted area: the target plus padding, clipped to the viewport. */
export function spotlightRect(target: Rect, vp: Size, pad = 6): Rect {
  const top = Math.max(0, target.top - pad);
  const left = Math.max(0, target.left - pad);
  const bottom = Math.min(vp.height, target.top + target.height + pad);
  const right = Math.min(vp.width, target.left + target.width + pad);
  return { top, left, width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
}

/** Where the popover goes: below the spotlight, else above, right, left; a
 *  target filling the screen gets the popover laid over its bottom edge. */
export function placePopover(spot: Rect | null, pop: Size, vp: Size): { top: number; left: number; placement: Placement } {
  const maxLeft = Math.max(MARGIN, vp.width - pop.width - MARGIN);
  const maxTop = Math.max(MARGIN, vp.height - pop.height - MARGIN);
  if (!spot) {
    return { top: clamp((vp.height - pop.height) / 2, MARGIN, maxTop), left: clamp((vp.width - pop.width) / 2, MARGIN, maxLeft), placement: 'center' };
  }
  const centerX = clamp(spot.left + spot.width / 2 - pop.width / 2, MARGIN, maxLeft);
  const centerY = clamp(spot.top + spot.height / 2 - pop.height / 2, MARGIN, maxTop);
  const below = spot.top + spot.height + GAP;
  if (below + pop.height <= vp.height - MARGIN) return { top: below, left: centerX, placement: 'bottom' };
  const above = spot.top - GAP - pop.height;
  if (above >= MARGIN) return { top: above, left: centerX, placement: 'top' };
  const right = spot.left + spot.width + GAP;
  if (right + pop.width <= vp.width - MARGIN) return { top: centerY, left: right, placement: 'right' };
  const left = spot.left - GAP - pop.width;
  if (left >= MARGIN) return { top: centerY, left, placement: 'left' };
  return { top: maxTop, left: centerX, placement: 'over' };
}

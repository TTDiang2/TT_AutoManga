import type { Panel } from '../../types';

/** The guided "Create" flow, in order. */
export const STEPS = ['story', 'panels', 'look', 'art', 'pages', 'finish'] as const;
export type StepId = typeof STEPS[number];

export type PromptFormat = 'danbooru' | 'prose';

export interface WizardState {
  projectId: string | null;
  step: StepId;
  storyText: string;
  detailLevel: number;
  reading: 'rtl' | 'ltr';
  promptFormat: PromptFormat;
  panelsPerPage: number;
  dynamic: boolean;
  coverPageId: string | null;
}

export const DEFAULT_STATE: WizardState = {
  projectId: null,
  step: 'story',
  storyText: '',
  detailLevel: 3,
  reading: 'rtl',
  promptFormat: 'danbooru',
  panelsPerPage: 4,
  dynamic: false,
  coverPageId: null,
};

const STORAGE_KEY = 'automanga-wizard';

/** Restores the saved wizard; unknown or broken values fall back to defaults. */
export function loadState(raw: string | null): WizardState {
  if (!raw) return { ...DEFAULT_STATE };
  try {
    const v = JSON.parse(raw) as Partial<WizardState>;
    const s = { ...DEFAULT_STATE, ...v };
    if (!STEPS.includes(s.step)) s.step = 'story';
    if (s.reading !== 'ltr') s.reading = 'rtl';
    if (s.promptFormat !== 'prose') s.promptFormat = 'danbooru';
    s.detailLevel = clamp(Math.round(Number(s.detailLevel) || 3), 1, 5);
    s.panelsPerPage = clamp(Math.round(Number(s.panelsPerPage) || 4), 1, 8);
    s.dynamic = !!s.dynamic;
    if (typeof s.projectId !== 'string' || !s.projectId) s.projectId = null;
    if (typeof s.coverPageId !== 'string' || !s.coverPageId) s.coverPageId = null;
    if (typeof s.storyText !== 'string') s.storyText = '';
    return s;
  } catch {
    return { ...DEFAULT_STATE };
  }
}

export function readSavedState(): WizardState {
  try {
    return loadState(localStorage.getItem(STORAGE_KEY));
  } catch {
    return { ...DEFAULT_STATE };
  }
}

export function writeSavedState(s: WizardState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    // private window / storage blocked: the wizard still works, it just won't resume
  }
}

function clamp(n: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, n));
}

export interface ProjectFacts {
  hasProject: boolean;
  panels: number;
  panelsWithImage: number;
  pages: number;
}

/** The furthest step the user may jump to, given what the project already has. */
export function maxReachableStep(f: ProjectFacts): number {
  if (!f.hasProject) return 0;
  if (f.panels === 0) return 1;
  if (f.panelsWithImage === 0) return 3;
  if (f.pages === 0) return 4;
  return 5;
}

/** "Anna, Ben ,, anna" → ["Anna", "Ben"] (case-insensitive dedupe, order kept). */
export function parseNames(text: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of text.split(/[,，、]/)) {
    const name = raw.trim();
    if (!name || seen.has(name.toLowerCase())) continue;
    seen.add(name.toLowerCase());
    out.push(name);
  }
  return out;
}

/** Every character named on any panel, in order of first appearance. */
export function castFromPanels(panels: Pick<Panel, 'characters'>[]): string[] {
  return parseNames(panels.flatMap(p => p.characters || []).join(','));
}

/** The prompt sent for a panel: an enhanced prompt from the Prompt Lab when
 *  it matches the chosen format, else the scene itself. Style, characters and
 *  shot are injected by the backend. */
export function promptForPanel(panel: Panel, format: PromptFormat): string {
  const enhanced = format === 'prose'
    ? panel.prompt?.turbo
    : (panel.prompt?.tags || []).map(t => t.trim()).filter(Boolean).join(', ');
  return (enhanced || '').trim() || panel.scene.trim();
}

/** Guess the prompt format from a SwarmUI model name. */
export function guessPromptFormat(model: string): PromptFormat {
  return /qwen|flux|hidream|wan|sd3|kolors/i.test(model) ? 'prose' : 'danbooru';
}

/** Panels with an empty scene, as 1-based numbers (the backend rejects them). */
export function emptyScenes(panels: Pick<Panel, 'scene'>[]): number[] {
  return panels.flatMap((p, i) => (p.scene.trim() ? [] : [i + 1]));
}

export function newPanel(existing: Pick<Panel, 'id'>[]): Panel {
  const used = new Set(existing.map(p => p.id));
  let n = existing.length + 1;
  while (used.has(`panel_${n}`)) n++;
  return { id: `panel_${n}`, order: existing.length, scene: '', characters: [], dialogue: '', prompt: {} };
}

export function movePanel<T>(list: T[], from: number, to: number): T[] {
  if (to < 0 || to >= list.length || from === to) return list;
  const next = list.slice();
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

/** Style presets offered on the Look step. */
export const STYLE_PRESETS: { id: string; prompt: string }[] = [
  { id: 'manga', prompt: 'monochrome manga, screentone, clean ink lineart, high contrast' },
  { id: 'western', prompt: 'western comic book style, bold ink outlines, flat colors, halftone shading' },
  { id: 'webtoon', prompt: 'webtoon style, soft cel shading, vibrant colors, clean lineart' },
  { id: 'watercolor', prompt: 'watercolor illustration, soft washes, paper texture, muted palette' },
  { id: 'ink', prompt: 'chinese ink painting style, ink (medium), muted colors, brush strokes' },
  { id: 'noir', prompt: 'noir comic, heavy shadows, black and white, dramatic lighting' },
];

/** Vertical balloons suit CJK dialogue; Latin text set vertically reads one
 *  letter per line. True when most dialogue letters are CJK. */
export function prefersVerticalBubbles(panels: Pick<Panel, 'dialogue'>[]): boolean {
  const text = panels.map(p => p.dialogue || '').join('');
  const cjk = (text.match(/[぀-ヿ㐀-鿿豈-﫿가-힯]/g) || []).length;
  const latin = (text.match(/[A-Za-z]/g) || []).length;
  return cjk > 0 && cjk * 3 >= latin;   // a CJK glyph carries roughly a word's worth
}

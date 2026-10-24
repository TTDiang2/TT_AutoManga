import { create } from 'zustand';
import type {
  ComposerPage,
  ComposerElement,
  ComposerTemplate,
  BubbleType,
  ImageSlotElement,
  ImageElement,
  PageImageElement,
  QuadCorners,
  CornerPoint,
  SavedTemplate,
} from '../types';
import { DEFAULT_CORNERS } from '../types';

const r2 = (n: number) => Math.round(n * 100) / 100;

/**
 * Generate image-slot elements from a row specification.
 * Each number in `rows` is the column count for that row.
 * All rows share equal height. Margin/gap are in canvas-%.
 *
 * Example: genRows([2, 3]) → row 1 has 2 equal cols, row 2 has 3 equal cols.
 */
function genRows(
  rows: number[],
  opts: { margin?: number; gap?: number; labelStart?: number } = {},
) {
  const margin = opts.margin ?? 2;
  const gap = opts.gap ?? 2;
  const labelStart = opts.labelStart ?? 1;
  const nRows = rows.length;
  const rowH = (100 - 2 * margin - (nRows - 1) * gap) / nRows;

  const elements: {
    type: 'image-slot';
    x: number; y: number; width: number; height: number;
    rotation: number; label: string;
  }[] = [];

  let idx = labelStart;
  let y = margin;

  for (const cols of rows) {
    const colW = (100 - 2 * margin - (cols - 1) * gap) / cols;
    let x = margin;
    for (let c = 0; c < cols; c++) {
      elements.push({
        type: 'image-slot',
        x: r2(x), y: r2(y),
        width: r2(colW), height: r2(rowH),
        rotation: 0,
        label: String(idx),
      });
      x += colW + gap;
      idx++;
    }
    y += rowH + gap;
  }
  return elements;
}

const M = 2; // default margin %
const G = 2; // default gap %

const TEMPLATES: ComposerTemplate[] = [
  {
    id: 'blank',
    name: 'Blank',
    nameZh: '空白页',
    width: 600,
    height: 900,
    elements: [],
  },
  // --- Manga layouts (margin=2, gap=2) ---
  {
    id: 'manga-2v',
    name: 'Manga 2V',
    nameZh: '漫画 2竖',
    width: 600, height: 900,
    elements: genRows([1, 1], { margin: M, gap: G }),
  },
  {
    id: 'manga-2h',
    name: 'Manga 2H',
    nameZh: '漫画 2横',
    width: 600, height: 900,
    elements: genRows([2], { margin: M, gap: G }),
  },
  {
    id: 'manga-3',
    name: 'Manga 3',
    nameZh: '漫画 3格',
    width: 600, height: 900,
    elements: genRows([1, 2], { margin: M, gap: G }),
  },
  {
    id: 'manga-4',
    name: 'Manga 4',
    nameZh: '漫画 4格',
    width: 600, height: 900,
    elements: genRows([2, 2], { margin: M, gap: G }),
  },
  {
    id: 'manga-6',
    name: 'Manga 6',
    nameZh: '漫画 6格',
    width: 600, height: 900,
    elements: genRows([2, 2, 2], { margin: M, gap: G }),
  },
  {
    id: 'manga-8',
    name: 'Manga 8',
    nameZh: '漫画 8格',
    width: 600, height: 900,
    elements: genRows([4, 4], { margin: M, gap: G }),
  },
  // --- Flexible column layouts (margin=2, gap=2) ---
  {
    id: 'grid-12',
    name: 'Grid 1+2',
    nameZh: '1+2 布局',
    width: 600, height: 900,
    elements: genRows([1, 2], { margin: M, gap: G }),
  },
  {
    id: 'grid-21',
    name: 'Grid 2+1',
    nameZh: '2+1 布局',
    width: 600, height: 900,
    elements: genRows([2, 1], { margin: M, gap: G }),
  },
  {
    id: 'grid-23',
    name: 'Grid 2+3',
    nameZh: '2+3 布局',
    width: 600, height: 900,
    elements: genRows([2, 3], { margin: M, gap: G }),
  },
  {
    id: 'grid-32',
    name: 'Grid 3+2',
    nameZh: '3+2 布局',
    width: 600, height: 900,
    elements: genRows([3, 2], { margin: M, gap: G }),
  },
  {
    id: 'grid-232',
    name: 'Grid 2+3+2',
    nameZh: '2+3+2 布局',
    width: 600, height: 900,
    elements: genRows([2, 3, 2], { margin: M, gap: G }),
  },
  {
    id: 'grid-323',
    name: 'Grid 3+2+3',
    nameZh: '3+2+3 布局',
    width: 600, height: 900,
    elements: genRows([3, 2, 3], { margin: M, gap: G }),
  },
  {
    id: 'grid-223',
    name: 'Grid 2+2+3',
    nameZh: '2+2+3 布局',
    width: 600, height: 900,
    elements: genRows([2, 2, 3], { margin: M, gap: G }),
  },
  // --- Hero / emphasis layouts (large frame in bottom-right) ---
  {
    id: 'hero-br-4',
    name: 'Hero BR',
    nameZh: '强调·右下大',
    width: 600, height: 900,
    elements: [
      { type: 'image-slot', x: 2, y: 2,    width: 30, height: 47, rotation: 0, label: '1' },
      { type: 'image-slot', x: 34, y: 2,   width: 30, height: 47, rotation: 0, label: '2' },
      { type: 'image-slot', x: 2, y: 51,   width: 30, height: 47, rotation: 0, label: '3' },
      { type: 'image-slot', x: 34, y: 51,  width: 64, height: 47, rotation: 0, label: '4' },
    ],
  },
  {
    id: 'hero-br-wide',
    name: 'Hero BR Wide',
    nameZh: '强调·右下宽',
    width: 600, height: 900,
    elements: [
      { type: 'image-slot', x: 2, y: 2,    width: 96, height: 30, rotation: 0, label: '1' },
      { type: 'image-slot', x: 2, y: 34,   width: 30, height: 64, rotation: 0, label: '2' },
      { type: 'image-slot', x: 34, y: 34,  width: 64, height: 64, rotation: 0, label: '3' },
    ],
  },
  {
    id: 'hero-splash',
    name: 'Hero Splash',
    nameZh: '强调·大特写',
    width: 600, height: 900,
    elements: [
      { type: 'image-slot', x: 2, y: 2,    width: 30, height: 30, rotation: 0, label: '1' },
      { type: 'image-slot', x: 34, y: 2,   width: 30, height: 30, rotation: 0, label: '2' },
      { type: 'image-slot', x: 66, y: 2,   width: 32, height: 30, rotation: 0, label: '3' },
      { type: 'image-slot', x: 2, y: 34,   width: 30, height: 64, rotation: 0, label: '4' },
      { type: 'image-slot', x: 34, y: 34,  width: 64, height: 64, rotation: 0, label: '5' },
    ],
  },
  // --- Photo layouts (keep existing, already have built-in margins) ---
  {
    id: 'photo-full',
    name: 'Photo Full',
    nameZh: '写真全幅',
    width: 600, height: 900,
    elements: genRows([1], { margin: M, gap: G }),
  },
  {
    id: 'photo-grid-4',
    name: 'Photo Grid 4',
    nameZh: '写真 4格',
    width: 600, height: 900,
    elements: genRows([2, 2], { margin: M, gap: G }),
  },
  {
    id: 'photo-grid-9',
    name: 'Photo Grid 9',
    nameZh: '写真 9格',
    width: 600, height: 900,
    elements: genRows([3, 3, 3], { margin: M, gap: G }),
  },
];

export { TEMPLATES };

interface HistoryEntry {
  pages: ComposerPage[];
}

interface ComposerStore {
  pages: ComposerPage[];
  currentPageId: string | null;
  selectedElementId: string | null;
  activeTool: 'select' | 'text' | 'bubble' | 'crop' | 'split';
  activeBubbleType: BubbleType;
  zoom: number;

  /** User-saved templates loaded from backend (`/api/composer/templates/`). */
  userTemplates: SavedTemplate[];

  _history: HistoryEntry[];
  _historyIndex: number;

  addPage: (templateId?: string) => void;
  removePage: (pageId: string) => void;
  setCurrentPage: (pageId: string) => void;
  duplicatePage: (pageId: string) => void;
  reorderPages: (fromIdx: number, toIdx: number) => void;
  applyTemplateToPage: (pageId: string, templateId: string) => void;
  /** Apply a user-saved template (by id) to the given page. */
  applyUserTemplate: (pageId: string, templateId: string) => void;

  addElement: (element: ComposerElement) => void;
  updateElement: (elementId: string, updates: Partial<ComposerElement>) => void;
  removeElement: (elementId: string) => void;
  selectElement: (elementId: string | null) => void;
  convertSlotToImage: (elementId: string, src: string) => void;

  /** Add a new blank image-slot at canvas center, selecting it. */
  addFrame: () => void;
  /**
   * Cut one rectangular frame (image-slot) into two along a page-space
   * axis line, leaving a gutter. Returns the two new element ids, or null
   * when the element isn't splittable / the cut falls outside.
   */
  splitFrame: (elementId: string, axis: 'x' | 'y', cutPct: number,
               gutterPct?: number) => [string, string] | null;
  /**
   * Empty-canvas variant: drag a line on an empty page and it becomes the
   * gutter between two new frames spanning the page.
   */
  createSplitPair: (axis: 'x' | 'y', cutPct: number,
                    gutterPct?: number, marginPct?: number) => [string, string] | null;
  /**
   * Add a new blank page-image (breakout image) at canvas center, selecting it.
   * Page-image is a free-floating image that is not part of any template — it
   * can be deformed, dragged, and scaled independently. It starts without a
   * src; the caller is expected to open the ImagePicker (or set src directly)
   * immediately after.
   */
  addPageImage: () => void;
  /**
   * Apply auto-gap to all image-slot/image elements on the current page.
   * For each pair of frames whose bounding boxes share a touching edge
   * (within tolerance), shrink each side by gapPercent/2 along that axis.
   * Corners are preserved relative to the (now smaller) bounding box,
   * so existing quadrilateral shapes stay visually intact.
   */
  autoGap: (gapPercent: number) => void;
  /** Apply a frame-border width to every image-slot / image on the current page. */
  setAllFrameBorders: (width: number) => void;
  /**
   * Snap all image-slot / image / page-image frames so edges near the page
   * boundary become parallel to the boundary at the given margin.
   * Only edges whose both endpoints are within margin+2% of the canvas edge
   * are adjusted. Edge-adjacent y-coordinates are NOT changed — only the x
   * (for left/right) or y (for top/bottom) coordinate is unified.
   */
  snapFramesToEdge: (margin?: number) => void;

  setActiveTool: (tool: ComposerStore['activeTool']) => void;
  setActiveBubbleType: (bt: BubbleType) => void;
  setZoom: (zoom: number) => void;

  undo: () => void;
  redo: () => void;
  setPages: (pages: ComposerPage[]) => void;
  _pushHistory: () => void;

  /** Load all user-saved templates from backend, store into `userTemplates`. */
  loadUserTemplates: () => Promise<void>;
  /**
   * Save the current page's geometry as a new user template.
   * Image payload is stripped — the saved template contains slots only.
   * Returns the new template id on success.
   */
  saveAsUserTemplate: (name: string) => Promise<string | null>;
  /** Delete a user-saved template by id (backend + local state). */
  deleteUserTemplate: (templateId: string) => Promise<void>;

  /**
   * Transient request to open the ImagePicker for a frame element. The Canvas
   * component watches this and renders the picker when set. Once an image is
   * selected (or the picker is dismissed), the value resets to `null`.
   * - `kind: 'slot'`        — fill an existing image-slot (converts to image)
   * - `kind: 'pageImage'`   — set src on a page-image element
   * - `kind: 'newPageImage'`— call addPageImage first, then open picker for it
   */
  imagePickerRequest: { kind: 'slot' | 'pageImage' | 'newPageImage'; id: string } | null;
  openImagePicker: (req: { kind: 'slot' | 'pageImage' | 'newPageImage'; id: string }) => void;
  closeImagePicker: () => void;
}

let idCounter = 0;
const uid = () => `el_${Date.now()}_${++idCounter}`;
const pageUid = () => `page_${Date.now()}_${++idCounter}`;

function templateToElements(template: ComposerTemplate): ComposerElement[] {
  return template.elements.map((el: Partial<ComposerElement>, i: number) => ({
    ...el,
    id: uid(),
    zIndex: i,
    locked: false,
    visible: true,
  })) as ComposerElement[];
}

export const useComposerStore = create<ComposerStore>()((set, get) => ({
  pages: [],
  currentPageId: null,
  selectedElementId: null,
  activeTool: 'select',
  activeBubbleType: 'speech',
  zoom: 0.6,

  userTemplates: [],

  imagePickerRequest: null,

  _history: [],
  _historyIndex: -1,

  _pushHistory: () => {
    const { pages, _history, _historyIndex } = get();
    const newHistory = _history.slice(0, _historyIndex + 1);
    newHistory.push({ pages: JSON.parse(JSON.stringify(pages)) });
    if (newHistory.length > 50) newHistory.shift();
    set({ _history: newHistory, _historyIndex: newHistory.length - 1 });
  },

  addPage: (templateId = 'blank') => {
    const template = TEMPLATES.find(t => t.id === templateId) || TEMPLATES[0];
    const newPage: ComposerPage = {
      id: pageUid(),
      name: `Page ${get().pages.length + 1}`,
      templateId,
      width: template.width,
      height: template.height,
      elements: templateToElements(template),
      order: get().pages.length,
    };
    get()._pushHistory();
    set(state => ({
      pages: [...state.pages, newPage],
      currentPageId: newPage.id,
      selectedElementId: null,
    }));
  },

  removePage: (pageId) => {
    const { pages, currentPageId } = get();
    if (pages.length <= 1) return;
    get()._pushHistory();
    const newPages = pages.filter(p => p.id !== pageId);
    const newCurrentId = currentPageId === pageId
      ? (newPages[0]?.id || null)
      : currentPageId;
    set({ pages: newPages, currentPageId: newCurrentId, selectedElementId: null });
  },

  setCurrentPage: (pageId) => set({ currentPageId: pageId, selectedElementId: null }),

  duplicatePage: (pageId) => {
    const { pages } = get();
    const source = pages.find(p => p.id === pageId);
    if (!source) return;
    get()._pushHistory();
    const newPage: ComposerPage = {
      ...JSON.parse(JSON.stringify(source)),
      id: pageUid(),
      name: `${source.name} copy`,
      order: pages.length,
    };
    newPage.elements = newPage.elements.map(el => ({ ...el, id: uid() }));
    set(state => ({
      pages: [...state.pages, newPage],
      currentPageId: newPage.id,
    }));
  },

  reorderPages: (fromIdx, toIdx) => {
    get()._pushHistory();
    set(state => {
      const newPages = [...state.pages];
      const [moved] = newPages.splice(fromIdx, 1);
      newPages.splice(toIdx, 0, moved);
      return { pages: newPages.map((p, i) => ({ ...p, order: i })) };
    });
  },

  applyTemplateToPage: (pageId, templateId) => {
    const template = TEMPLATES.find(t => t.id === templateId);
    if (!template) return;
    get()._pushHistory();
    const newElements = templateToElements(template);
    set(state => ({
      pages: state.pages.map(p =>
        p.id === pageId
          ? { ...p, templateId, elements: newElements, width: template.width, height: template.height }
          : p
      ),
      selectedElementId: null,
    }));
  },

  applyUserTemplate: (pageId, templateId) => {
    const template = get().userTemplates.find(t => t.id === templateId);
    if (!template) {
      console.warn('[composer] applyUserTemplate: template not found in store', templateId);
      return;
    }
    get()._pushHistory();
    // Saved templates only carry geometry (no id/zIndex/locked/visible),
    // so templateToElements' spread-then-augment pattern works on them too.
    const newElements = templateToElements(template as unknown as ComposerTemplate);
    set(state => ({
      pages: state.pages.map(p =>
        p.id === pageId
          ? {
              ...p,
              templateId: `user:${templateId}`,
              elements: newElements,
              width: template.width,
              height: template.height,
            }
          : p
      ),
      selectedElementId: null,
    }));
  },

  addElement: (element) => {
    get()._pushHistory();
    set(state => {
      const pageIdx = state.pages.findIndex(p => p.id === state.currentPageId);
      if (pageIdx === -1) return state;
      const pages = [...state.pages];
      pages[pageIdx] = {
        ...pages[pageIdx],
        elements: [...pages[pageIdx].elements, element],
      };
      return { pages, selectedElementId: element.id };
    });
  },

  updateElement: (elementId, updates) => {
    set(state => {
      const pageIdx = state.pages.findIndex(p => p.id === state.currentPageId);
      if (pageIdx === -1) return state;
      const pages = [...state.pages];
      pages[pageIdx] = {
        ...pages[pageIdx],
        elements: pages[pageIdx].elements.map(el =>
          el.id === elementId ? { ...el, ...updates } : el
        ) as ComposerElement[],
      };
      return { pages };
    });
  },

  removeElement: (elementId) => {
    get()._pushHistory();
    set(state => {
      const pageIdx = state.pages.findIndex(p => p.id === state.currentPageId);
      if (pageIdx === -1) return state;
      const pages = [...state.pages];
      pages[pageIdx] = {
        ...pages[pageIdx],
        elements: pages[pageIdx].elements.filter(el => el.id !== elementId),
      };
      return { pages, selectedElementId: state.selectedElementId === elementId ? null : state.selectedElementId };
    });
  },

  selectElement: (elementId) => set({ selectedElementId: elementId }),

  convertSlotToImage: (elementId, src) => {
    get()._pushHistory();
    set(state => {
      const pageIdx = state.pages.findIndex(p => p.id === state.currentPageId);
      if (pageIdx === -1) return state;
      const pages = [...state.pages];
      const el = pages[pageIdx].elements.find(e => e.id === elementId);
      if (!el) return state;
      if (el.type === 'image-slot') {
        const { label, ...base } = el;
        const imageEl = { ...base, type: 'image' as const, src };
        pages[pageIdx] = {
          ...pages[pageIdx],
          elements: pages[pageIdx].elements.map(e => e.id === elementId ? imageEl : e),
        };
      } else if (el.type === 'image') {
        // Replace image on an already-converted element
        pages[pageIdx] = {
          ...pages[pageIdx],
          elements: pages[pageIdx].elements.map(e => e.id === elementId ? { ...e, src } : e),
        };
      } else {
        return state;
      }
      return { pages };
    });
  },

  addFrame: () => {
    const page = get().pages.find(p => p.id === get().currentPageId);
    if (!page) return;
    get()._pushHistory();
    const newEl: ImageSlotElement = {
      id: uid(),
      type: 'image-slot',
      x: 35,
      y: 35,
      width: 30,
      height: 30,
      rotation: 0,
      zIndex: page.elements.length,
      locked: false,
      visible: true,
      label: `Frame ${page.elements.length + 1}`,
    };
    set(state => {
      const pageIdx = state.pages.findIndex(p => p.id === state.currentPageId);
      if (pageIdx === -1) return state;
      const pages = [...state.pages];
      pages[pageIdx] = {
        ...pages[pageIdx],
        elements: [...pages[pageIdx].elements, newEl],
      };
      return { pages, selectedElementId: newEl.id };
    });
  },

  splitFrame: (elementId, axis, cutPct, gutterPct = 2) => {
    const page = get().pages.find(p => p.id === get().currentPageId);
    const el = page?.elements.find(e => e.id === elementId);
    // only plain rectangles split cleanly — corner-deformed frames keep their shape
    if (!page || !el || el.type !== 'image-slot' || el.corners) return null;
    const g = gutterPct / 2;
    const minSize = 5;
    const make = (rect: { x: number; y: number; width: number; height: number }, suffix: string): ImageSlotElement => ({
      id: uid(),
      type: 'image-slot',
      x: Math.round(rect.x * 100) / 100,
      y: Math.round(rect.y * 100) / 100,
      width: Math.round(rect.width * 100) / 100,
      height: Math.round(rect.height * 100) / 100,
      rotation: 0,
      zIndex: el.zIndex,
      locked: false,
      visible: true,
      label: `${el.label || 'Frame'}${suffix}`,
    });
    let pair: [{ x: number; y: number; width: number; height: number },
               { x: number; y: number; width: number; height: number }];
    if (axis === 'x') {
      if (cutPct <= el.x + minSize + g || cutPct >= el.x + el.width - minSize - g) return null;
      pair = [
        { x: el.x, y: el.y, width: cutPct - g - el.x, height: el.height },
        { x: cutPct + g, y: el.y, width: el.x + el.width - (cutPct + g), height: el.height },
      ];
    } else {
      if (cutPct <= el.y + minSize + g || cutPct >= el.y + el.height - minSize - g) return null;
      pair = [
        { x: el.x, y: el.y, width: el.width, height: cutPct - g - el.y },
        { x: el.x, y: cutPct + g, width: el.width, height: el.y + el.height - (cutPct + g) },
      ];
    }
    const [a, b] = [make(pair[0], 'a'), make(pair[1], 'b')];
    get()._pushHistory();
    set(state => {
      const pageIdx = state.pages.findIndex(p => p.id === state.currentPageId);
      if (pageIdx === -1) return state;
      const pages = [...state.pages];
      pages[pageIdx] = {
        ...pages[pageIdx],
        elements: pages[pageIdx].elements.flatMap(e =>
          e.id === elementId ? [a, b] : [e]),
      };
      return { pages, selectedElementId: b.id };
    });
    return [a.id, b.id];
  },

  createSplitPair: (axis, cutPct, gutterPct = 2, marginPct = 2) => {
    const page = get().pages.find(p => p.id === get().currentPageId);
    if (!page) return null;
    const g = gutterPct / 2;
    const lo = marginPct, hi = 100 - marginPct;
    if (cutPct <= lo + 5 || cutPct >= hi - 5) return null;
    get()._pushHistory();
    const mk = (rect: { x: number; y: number; width: number; height: number }, label: string): ImageSlotElement => ({
      id: uid(), type: 'image-slot', rotation: 0, locked: false, visible: true,
      zIndex: page.elements.length,
      x: Math.round(rect.x * 100) / 100, y: Math.round(rect.y * 100) / 100,
      width: Math.round(rect.width * 100) / 100, height: Math.round(rect.height * 100) / 100,
      label,
    });
    const pair = axis === 'x'
      ? [mk({ x: lo, y: lo, width: cutPct - g - lo, height: hi - lo }, 'Frame 1'),
         mk({ x: cutPct + g, y: lo, width: hi - (cutPct + g), height: hi - lo }, 'Frame 2')]
      : [mk({ x: lo, y: lo, width: hi - lo, height: cutPct - g - lo }, 'Frame 1'),
         mk({ x: lo, y: cutPct + g, width: hi - lo, height: hi - (cutPct + g) }, 'Frame 2')];
    set(state => {
      const pageIdx = state.pages.findIndex(p => p.id === state.currentPageId);
      if (pageIdx === -1) return state;
      const pages = [...state.pages];
      pages[pageIdx] = {
        ...pages[pageIdx],
        elements: [...pages[pageIdx].elements, ...pair],
      };
      return { pages, selectedElementId: pair[1].id };
    });
    return [pair[0].id, pair[1].id];
  },

  addPageImage: () => {
    const page = get().pages.find(p => p.id === get().currentPageId);
    if (!page) return;
    get()._pushHistory();
    const newEl: PageImageElement = {
      id: uid(),
      type: 'page-image',
      x: 35,
      y: 35,
      width: 30,
      height: 30,
      rotation: 0,
      zIndex: page.elements.length,
      locked: false,
      visible: true,
      src: '',
    };
    set(state => {
      const pageIdx = state.pages.findIndex(p => p.id === state.currentPageId);
      if (pageIdx === -1) return state;
      const pages = [...state.pages];
      pages[pageIdx] = {
        ...pages[pageIdx],
        elements: [...pages[pageIdx].elements, newEl],
      };
      return { pages, selectedElementId: newEl.id };
    });
  },

  autoGap: (gapPercent) => {
    const page = get().pages.find(p => p.id === get().currentPageId);
    console.log('[autoGap] called gapPercent=', gapPercent, 'page=', page?.id, 'elements=', page?.elements.length);
    if (!page) return;

    // Working copy: each frame carries its bbox (canvas %) and a mutable
    // deep copy of its corners (bbox %).  Frames without corners get the
    // default rectangle so the algorithm can treat everything uniformly.
    type Frame = {
      id: string;
      x: number; y: number; w: number; h: number;
      corners: QuadCorners;
      hadCorners: boolean; // whether the original element explicitly set corners
    };
    const frames: Frame[] = page.elements
      // page-image is intentionally excluded — it's a free-floating breakout
      // element and shouldn't be auto-aligned to the panel grid.
      .filter(el => el.type === 'image-slot' || el.type === 'image')
      .map(el => {
        const c = el.corners ?? DEFAULT_CORNERS;
        return {
          id: el.id,
          x: el.x, y: el.y, w: el.width, h: el.height,
          corners: {
            tl: { x: c.tl.x, y: c.tl.y },
            tr: { x: c.tr.x, y: c.tr.y },
            br: { x: c.br.x, y: c.br.y },
            bl: { x: c.bl.x, y: c.bl.y },
          },
          hadCorners: !!el.corners,
        };
      });
    if (frames.length < 2) {
      console.log('[autoGap] only', frames.length, 'frame(s) — nothing to gap');
      return;
    }

    console.log('[autoGap] processing', frames.length, 'frames, gap=', gapPercent + '%');
    const TOL = 0.5; // canvas-% tolerance for "touching"
    const modified = new Set<string>();

    // --- geometry helpers (all canvas-% space) ---
    const canvasPos = (f: Frame, c: CornerPoint): CornerPoint => ({
      x: f.x + (c.x / 100) * f.w,
      y: f.y + (c.y / 100) * f.h,
    });
    const toBboxPct = (f: Frame, pt: CornerPoint): CornerPoint => ({
      x: f.w > 0 ? ((pt.x - f.x) / f.w) * 100 : 0,
      y: f.h > 0 ? ((pt.y - f.y) / f.h) * 100 : 0,
    });
    const clampCorner = (v: number) => Math.max(-100, Math.min(200, v));
    const norm2 = (vx: number, vy: number): [number, number] => {
      const m = Math.hypot(vx, vy);
      return m > 1e-9 ? [vx / m, vy / m] : [0, 1];
    };

    /**
     * Parallelize two touching edges to their average direction and insert
     * a gap.  Each edge keeps its own midpoint (shifted perpendicular by
     * half the gap) and its own length.
     *
     * @param aTop/aBot   endpoints of A's touching edge (canvas %)
     * @param bTop/bBot   endpoints of B's touching edge (canvas %)
     * @param perpAx/perpAy  unit perpendicular pointing AWAY from B (for A)
     * @param perpBx/perpBy  unit perpendicular pointing AWAY from A (for B)
     * @param setA  callback to write A's new endpoints back as bbox-% corners
     * @param setB  callback to write B's new endpoints back as bbox-% corners
     */
    const parallelize = (
      aTop: CornerPoint, aBot: CornerPoint,
      bTop: CornerPoint, bBot: CornerPoint,
      perpAx: number, perpAy: number,
      perpBx: number, perpBy: number,
      half: number,
      setA: (topPct: CornerPoint, botPct: CornerPoint) => void,
      setB: (topPct: CornerPoint, botPct: CornerPoint) => void,
    ) => {
      const [dAx, dAy] = norm2(aBot.x - aTop.x, aBot.y - aTop.y);
      const [dBx, dBy] = norm2(bBot.x - bTop.x, bBot.y - bTop.y);
      // Average direction (bisector of the two edge directions)
      const [avgX, avgY] = norm2(dAx + dBx, dAy + dBy);
      const lenA = Math.hypot(aBot.x - aTop.x, aBot.y - aTop.y);
      const lenB = Math.hypot(bBot.x - bTop.x, bBot.y - bTop.y);
      const midAx = (aTop.x + aBot.x) / 2, midAy = (aTop.y + aBot.y) / 2;
      const midBx = (bTop.x + bBot.x) / 2, midBy = (bTop.y + bBot.y) / 2;
      // Shift midpoints perpendicular by half-gap
      const nMidAx = midAx + perpAx * half, nMidAy = midAy + perpAy * half;
      const nMidBx = midBx + perpBx * half, nMidBy = midBy + perpBy * half;
      setA(
        { x: nMidAx - avgX * lenA / 2, y: nMidAy - avgY * lenA / 2 },
        { x: nMidAx + avgX * lenA / 2, y: nMidAy + avgY * lenA / 2 },
      );
      setB(
        { x: nMidBx - avgX * lenB / 2, y: nMidBy - avgY * lenB / 2 },
        { x: nMidBx + avgX * lenB / 2, y: nMidBy + avgY * lenB / 2 },
      );
    };

    /** Horizontal touch: A's right edge meets B's left edge. */
    const doH = (A: Frame, B: Frame) => {
      const aTop = canvasPos(A, A.corners.tr), aBot = canvasPos(A, A.corners.br);
      const bTop = canvasPos(B, B.corners.tl), bBot = canvasPos(B, B.corners.bl);
      // Current visible spacing between A's right edge and B's left edge
      const aRightX = (aTop.x + aBot.x) / 2;
      const bLeftX = (bTop.x + bBot.x) / 2;
      const currentSpacing = bLeftX - aRightX;
      // Adjust to reach exactly gapPercent (positive = push apart, negative = pull together)
      const half = (gapPercent - currentSpacing) / 2;
      if (Math.abs(half) <= 0.001) return;
      parallelize(
        aTop, aBot, bTop, bBot,
        -1, 0,  // A shifts left
        1, 0,   // B shifts right
        half,
        (tp, bp) => {
          A.corners.tr = { x: clampCorner(toBboxPct(A, tp).x), y: clampCorner(toBboxPct(A, tp).y) };
          A.corners.br = { x: clampCorner(toBboxPct(A, bp).x), y: clampCorner(toBboxPct(A, bp).y) };
        },
        (tp, bp) => {
          B.corners.tl = { x: clampCorner(toBboxPct(B, tp).x), y: clampCorner(toBboxPct(B, tp).y) };
          B.corners.bl = { x: clampCorner(toBboxPct(B, bp).x), y: clampCorner(toBboxPct(B, bp).y) };
        },
      );
    };
    /** Vertical touch: A's bottom edge meets B's top edge. */
    const doV = (A: Frame, B: Frame) => {
      const aL = canvasPos(A, A.corners.bl), aR = canvasPos(A, A.corners.br);
      const bL = canvasPos(B, B.corners.tl), bR = canvasPos(B, B.corners.tr);
      // Current visible spacing between A's bottom edge and B's top edge
      const aBottomY = (aL.y + aR.y) / 2;
      const bTopY = (bL.y + bR.y) / 2;
      const currentSpacing = bTopY - aBottomY;
      // Adjust to reach exactly gapPercent (positive = push apart, negative = pull together)
      const half = (gapPercent - currentSpacing) / 2;
      if (Math.abs(half) <= 0.001) return;
      parallelize(
        aL, aR, bL, bR,
        0, -1,  // A shifts up
        0, 1,   // B shifts down
        half,
        (lp, rp) => {
          A.corners.bl = { x: clampCorner(toBboxPct(A, lp).x), y: clampCorner(toBboxPct(A, lp).y) };
          A.corners.br = { x: clampCorner(toBboxPct(A, rp).x), y: clampCorner(toBboxPct(A, rp).y) };
        },
        (lp, rp) => {
          B.corners.tl = { x: clampCorner(toBboxPct(B, lp).x), y: clampCorner(toBboxPct(B, lp).y) };
          B.corners.tr = { x: clampCorner(toBboxPct(B, rp).x), y: clampCorner(toBboxPct(B, rp).y) };
        },
      );
    };

    // Touch detection (bbox based).
    // "Touching" means: B sits beside A (no overlap) AND the spacing between
    // them is within the current gapPercent. This means:
    //   - manga templates (spacing=0) match when gapPercent>=0
    //   - photo-grid templates (spacing=2) match when gapPercent>=2
    //   - raising gapPercent on photo-grid still expands the gap
    const hTouch = (A: Frame, B: Frame) => {
      const gap = B.x - (A.x + A.w);
      return gap >= -TOL && gap <= gapPercent &&
        (A.y + A.h) > B.y && (B.y + B.h) > A.y;
    };
    const vTouch = (A: Frame, B: Frame) => {
      const gap = B.y - (A.y + A.h);
      return gap >= -TOL && gap <= gapPercent &&
        (A.x + A.w) > B.x && (B.x + B.w) > A.x;
    };

    for (let i = 0; i < frames.length; i++) {
      for (let j = i + 1; j < frames.length; j++) {
        const A = frames[i], B = frames[j];
        if (hTouch(A, B)) { doH(A, B); modified.add(A.id); modified.add(B.id); }
        if (hTouch(B, A)) { doH(B, A); modified.add(A.id); modified.add(B.id); }
        if (vTouch(A, B)) { doV(A, B); modified.add(A.id); modified.add(B.id); }
        if (vTouch(B, A)) { doV(B, A); modified.add(A.id); modified.add(B.id); }
      }
    }

    if (modified.size === 0) {
      console.log('[autoGap] no touching frames detected');
      return;
    }
    console.log('[autoGap] modifying', modified.size, 'frames');
    get()._pushHistory();
    set(state => {
      const pageIdx = state.pages.findIndex(p => p.id === state.currentPageId);
      if (pageIdx === -1) return state;
      const pages = [...state.pages];
      pages[pageIdx] = {
        ...pages[pageIdx],
        elements: pages[pageIdx].elements.map(el => {
          if (!modified.has(el.id)) return el;
          const f = frames.find(fr => fr.id === el.id);
          if (!f) return el;
          return {
            ...el,
            corners: {
              tl: { x: f.corners.tl.x, y: f.corners.tl.y },
              tr: { x: f.corners.tr.x, y: f.corners.tr.y },
              br: { x: f.corners.br.x, y: f.corners.br.y },
              bl: { x: f.corners.bl.x, y: f.corners.bl.y },
            },
          } as ComposerElement;
        }),
      };
      console.log('[autoGap] wrote updated corners to', modified.size, 'elements');
      return { pages };
    });
  },

  setAllFrameBorders: (width) => {
    set(state => {
      const pageIdx = state.pages.findIndex(p => p.id === state.currentPageId);
      if (pageIdx === -1) return state;
      const pages = [...state.pages];
      pages[pageIdx] = {
        ...pages[pageIdx],
        elements: pages[pageIdx].elements.map(el => {
          if (el.type === 'image-slot' || el.type === 'image') {
            return { ...el, frameBorderWidth: width };
          }
          return el;
        }) as ComposerElement[],
      };
      return { pages };
    });
  },

  /** Snap frame edges near the page boundary to be parallel with a uniform margin. */
  snapFramesToEdge: (margin = 2) => {
    set(state => {
      const pageIdx = state.pages.findIndex(p => p.id === state.currentPageId);
      if (pageIdx === -1) return state;
      const pages = [...state.pages];
      const page = { ...pages[pageIdx] };
      const THRESHOLD = margin + 2; // % from page edge — anything closer gets snapped

      const toPageX = (el: ComposerElement, cx: number) => el.x + cx * el.width / 100;
      const toPageY = (el: ComposerElement, cy: number) => el.y + cy * el.height / 100;
      const fromPageX = (el: ComposerElement, px: number) => (px - el.x) * 100 / el.width;
      const fromPageY = (el: ComposerElement, py: number) => (py - el.y) * 100 / el.height;

      page.elements = page.elements.map(el => {
        if (el.type !== 'image-slot' && el.type !== 'image' && el.type !== 'page-image') return el;
        const c = el.corners;
        const corners = c ? {
          tl: { x: c.tl.x, y: c.tl.y },
          tr: { x: c.tr.x, y: c.tr.y },
          br: { x: c.br.x, y: c.br.y },
          bl: { x: c.bl.x, y: c.bl.y },
        } : {
          tl: { x: 0, y: 0 },
          tr: { x: 100, y: 0 },
          br: { x: 100, y: 100 },
          bl: { x: 0, y: 100 },
        };
        let changed = false;

        // Left edge (BL → TL): snap to vertical at page-x = margin
        if (toPageX(el, corners.bl.x) < THRESHOLD && toPageX(el, corners.tl.x) < THRESHOLD) {
          const sx = fromPageX(el, margin);
          corners.bl.x = sx; corners.tl.x = sx;
          changed = true;
        }
        // Right edge (TR → BR): snap to vertical at page-x = 100 - margin
        if (toPageX(el, corners.tr.x) > 100 - THRESHOLD && toPageX(el, corners.br.x) > 100 - THRESHOLD) {
          const sx = fromPageX(el, 100 - margin);
          corners.tr.x = sx; corners.br.x = sx;
          changed = true;
        }
        // Top edge (TL → TR): snap to horizontal at page-y = margin
        if (toPageY(el, corners.tl.y) < THRESHOLD && toPageY(el, corners.tr.y) < THRESHOLD) {
          const sy = fromPageY(el, margin);
          corners.tl.y = sy; corners.tr.y = sy;
          changed = true;
        }
        // Bottom edge (BR → BL): snap to horizontal at page-y = 100 - margin
        if (toPageY(el, corners.br.y) > 100 - THRESHOLD && toPageY(el, corners.bl.y) > 100 - THRESHOLD) {
          const sy = fromPageY(el, 100 - margin);
          corners.br.y = sy; corners.bl.y = sy;
          changed = true;
        }

        if (changed) return { ...el, corners };
        return el;
      }) as ComposerElement[];

      pages[pageIdx] = page;
      return { pages };
    });
  },

  setActiveTool: (tool) => set({ activeTool: tool }),
  setActiveBubbleType: (bt) => set({ activeBubbleType: bt }),
  setZoom: (zoom) => set({ zoom: Math.max(0.15, Math.min(3, zoom)) }),

  undo: () => {
    const { _history, _historyIndex } = get();
    if (_historyIndex <= 0) return;
    const newIndex = _historyIndex - 1;
    const entry = _history[newIndex];
    set({ pages: JSON.parse(JSON.stringify(entry.pages)), _historyIndex: newIndex, selectedElementId: null });
  },

  redo: () => {
    const { _history, _historyIndex } = get();
    if (_historyIndex >= _history.length - 1) return;
    const newIndex = _historyIndex + 1;
    const entry = _history[newIndex];
    set({ pages: JSON.parse(JSON.stringify(entry.pages)), _historyIndex: newIndex, selectedElementId: null });
  },

  setPages: (pages) => {
    set({
      pages,
      currentPageId: pages[0]?.id || null,
      selectedElementId: null,
      _history: [{ pages: JSON.parse(JSON.stringify(pages)) }],
      _historyIndex: 0,
    });
  },

  loadUserTemplates: async () => {
    try {
      const r = await fetch('/api/composer/templates/');
      if (!r.ok) {
        console.warn('[composer] loadUserTemplates: HTTP', r.status);
        return;
      }
      const data: SavedTemplate[] = await r.json();
      set({ userTemplates: Array.isArray(data) ? data : [] });
    } catch (err) {
      console.warn('[composer] loadUserTemplates failed:', err);
    }
  },

  saveAsUserTemplate: async (name: string) => {
    const page = get().pages.find(p => p.id === get().currentPageId);
    if (!page) return null;
    const id = `tpl_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    // Strip image payload + base fields; backend will also re-strip on its end.
    const sanitizedElements = page.elements
      .map(el => {
        // Keep geometry, label, type, corners. Drop src/image-specific bits.
        // (the extra optional fields only exist on some union members, hence
        // the widened pick)
        type ElementBits = Partial<Pick<ImageElement, 'src' | 'originalSrc' | 'cropArea'>>;
        const { id: _id, zIndex: _z, locked: _l, visible: _v,
                src: _s, originalSrc: _os, cropArea: _c,
                ...rest } = el as ComposerElement & ElementBits;
        // Downgrade image elements to empty slots (templates are geometry only).
        if (rest.type === 'image' || rest.type === 'page-image') {
          return { ...rest, type: 'image-slot' as const };
        }
        return rest;
      });
    const payload = {
      id,
      name,
      width: page.width,
      height: page.height,
      elements: sanitizedElements,
    };
    try {
      const r = await fetch('/api/composer/templates/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!r.ok) {
        console.warn('[composer] saveAsUserTemplate: HTTP', r.status, await r.text());
        return null;
      }
      // Refresh local list so the new template shows up immediately.
      await get().loadUserTemplates();
      return id;
    } catch (err) {
      console.warn('[composer] saveAsUserTemplate failed:', err);
      return null;
    }
  },

  deleteUserTemplate: async (templateId: string) => {
    try {
      const r = await fetch(`/api/composer/templates/${encodeURIComponent(templateId)}`, {
        method: 'DELETE',
      });
      if (!r.ok) {
        console.warn('[composer] deleteUserTemplate: HTTP', r.status);
        return;
      }
      set(state => ({ userTemplates: state.userTemplates.filter(t => t.id !== templateId) }));
    } catch (err) {
      console.warn('[composer] deleteUserTemplate failed:', err);
    }
  },

  openImagePicker: (req) => {
    if (req.kind === 'newPageImage') {
      // Create the page-image first, then request the picker for the new id.
      get().addPageImage();
      // addPageImage synchronously sets selectedElementId to the new id.
      const newId = get().selectedElementId;
      if (newId) {
        set({ imagePickerRequest: { kind: 'pageImage', id: newId } });
      } else {
        set({ imagePickerRequest: { kind: 'pageImage', id: req.id } });
      }
    } else {
      set({ imagePickerRequest: req });
    }
  },

  closeImagePicker: () => set({ imagePickerRequest: null }),
}));

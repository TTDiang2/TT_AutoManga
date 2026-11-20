/** The outline of a .comic script (Comics repo README, "Script format") for the editor's Outline panel and the
    AI rewrite's targets: its pages, its panels and the scenes they make.

    - Offsets are string indices (UTF-16 code units, as a textarea and the rewrite endpoint take them) of whole
      lines: a panel runs from its PANEL line to the line before the next PANEL/PAGE, a page from its PAGE line to
      the line before the next PAGE (its panels included); the last one runs to the end of the text. Lines are
      1-based. CRLF text works (offsets count the \r).
    - Panel ids are comic.js's: "2.3" (regular page 2, panel 3), "u1.2" (uncut page 1 — counting every PAGE uncut,
      todo slots too — panel 2), "4.u1" (the first PANEL uncut of regular page 4). Regular pages are numbered by
      count: a number after PAGE is ignored, as comic.js does.
    - place: carries over as comic.js does it: a regular panel from the regular panel before it, an uncut one from
      the panel before it in the script (regular or uncut).
    - Scenes: maximal runs of consecutive panels (script order, across pages) with the same place key and time
      (compared case-insensitively; "cafe" after "cafe, day" has no time, so it is another scene). A new one also
      starts on a regular/uncut page switch, and at a panel whose lettering starts with a CAPTION that reads like a
      scene change (sceneCaption below). A scene's range runs from its first panel's start to its last panel's
      end, so it may hold the PAGE header of a page it crosses.
    - It never throws: the editor text is live, half-typed and possibly invalid. Lines before the first PAGE and a
      PANEL before any PAGE are left out. */

export interface OutlinePage {
  id: string;                 // "3" or "u1"
  n: number | null;           // its regular page number
  uncutIndex: number | null;  // its PAGE uncut number
  title: string;              // the rest of the PAGE line: "PAGE 1 — Coffee" → "Coffee"
  uncut: boolean;
  todo: boolean;
  startOffset: number;
  endOffset: number;
  startLine: number;
  endLine: number;
  panels: string[];           // panel ids, in script order
}

export interface OutlinePanel {
  id: string;
  page: string;               // its page's id
  startOffset: number;
  endOffset: number;
  line: number;               // its PANEL line
  endLine: number;
  cast: string[];             // ids, left to right
  shot: string;
  place: string | null;       // the effective place key (after carry-over)
  time: string | null;
  ownPlace: boolean;          // it has its own place: line
  firstDescription: string;   // its first description line, shortened
  uncut: boolean;             // a PANEL uncut, or any panel of a PAGE uncut
  todo: boolean;              // PANEL uncut todo, or on a PAGE uncut todo
  captionBreak: boolean;      // its lettering starts with a scene-change caption
}

export interface OutlineScene {
  id: string;                 // "s1", "s2", ... in script order
  place: string | null;
  time: string | null;
  startOffset: number;
  endOffset: number;
  startLine: number;
  endLine: number;
  panels: string[];
  cast: string[];             // everyone on its panels, first appearance first
  uncut: boolean;             // every panel uncut
  todo: boolean;              // any panel a todo slot
}

export interface Outline {
  pages: OutlinePage[];
  scenes: OutlineScene[];
  panels: OutlinePanel[];
  length: number;             // the text's length
}

export type OutlineKind = 'page' | 'scene' | 'panel';
export type OutlineEntry = OutlinePage | OutlineScene | OutlinePanel;

const TIMES = new Set(['morning', 'day', 'evening', 'night', 'sunset', 'dusk', 'dawn']);
const UNCUT_RE = /^\s*(?:\d+\s+)?uncut\b(\s+todo\b)?/;
const SPEECH_RE = /^([A-Z][A-Z0-9_'.-]*(?: [A-Z][A-Z0-9_'.-]*)?)\s*(?:\(([^)]*)\))?\s*:\s*(.+)$/;
const KEY_RE = /^([a-z_]+)\s*:\s*(.*)$/i;
// keys that are not a picture description (the panel keys of lib/script.js, and page keys written in a panel)
const NOT_DESCRIPTION = new Set(['place', 'cast', 'seats', 'shot', 'seed', 'neg', 'prompt', 'model', 'regions', 'pairfix',
  'face', 'creativity', 'init', 'lora', 'ref', 'rating', 'layout', 'layout_uncut']);
const DESCRIPTION_MAX = 80;

/** A caption that opens a panel's lettering and says time has passed or the story moved: "Later", "Hours later",
    "A few days later", "Two weeks on", "That night", "The next morning", "The following day", "Meanwhile",
    "Elsewhere", "Earlier", "Tonight", "Monday" (any weekday), or a time stamp ("— 7:40", "7:40 a.m."). */
const QTY = String.raw`(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|twelve|a few|a couple of|a couple|few|several|some|many|\d+)`;
const UNITS = String.raw`(?:moments?|seconds?|minutes?|hours?|days?|nights?|weeks?|months?|years?)`;
const SCENE_WORDS = new RegExp(String.raw`^(?:` + [
  String.raw`(?:much |not long |some time |a little )?later`,
  String.raw`(?:${QTY} )?${UNITS} (?:later|after|on)`,
  String.raw`meanwhile`, String.raw`elsewhere`, String.raw`earlier`, String.raw`tonight`,
  String.raw`(?:the )?next (?:morning|day|night|evening|afternoon|week|weekend)`,
  String.raw`(?:that|this|the same|the following) (?:night|evening|morning|afternoon|day|weekend|week)`,
  String.raw`(?:on )?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?`,
].join('|') + String.raw`)(?![\w'])`, 'i');
const TIME_STAMP = /^(?:[—–]\s*\S|\d{1,2}[:.]\d{2}(?!\d))/;

export function sceneCaption(text: string): boolean {
  const s = text.trim().replace(/^["'“‘(]+/, '');
  return SCENE_WORDS.test(s) || TIME_STAMP.test(s);
}

/** "cafe, day" → { key: 'cafe', time: 'day' }, as lib/script.js parsePlace does. */
function parsePlace(s: string) {
  const parts = s.split(',').map(x => x.trim()).filter(Boolean);
  let time: string | null = null;
  if (parts.length > 1 && TIMES.has(parts[parts.length - 1].toLowerCase())) time = parts.pop()!.toLowerCase();
  return { key: parts.join(', '), time };
}

/** "mara(work, smile), nova" → ['mara', 'nova'] (top-level commas only; malformed entries are skipped). */
function castIds(s: string) {
  const out: string[] = [];
  let depth = 0, cur = '';
  const push = () => {
    const m = cur.trim().match(/^([A-Za-z0-9_]+)/);
    if (m) out.push(m[1].toLowerCase());
    cur = '';
  };
  for (const ch of s) {
    if (ch === '(') depth++;
    if (ch === ')') depth = Math.max(0, depth - 1);
    if (ch === ',' && depth === 0) push(); else cur += ch;
  }
  push();
  return out;
}

const shorten = (s: string) => (s.length > DESCRIPTION_MAX ? `${s.slice(0, DESCRIPTION_MAX - 1).trimEnd()}…` : s);

interface WorkPanel extends OutlinePanel { ownTime: string | null; onUncutPage: boolean; lettered: boolean }
interface WorkPage extends OutlinePage { regular: number; uncutPanels: number }

function parse(text: string): Outline {
  const pages: WorkPage[] = [];
  const panels: WorkPanel[] = [];
  let page: WorkPage | null = null;
  let panel: WorkPanel | null = null;
  let regularPages = 0, uncutPages = 0;
  let at = 0;
  const lines = text.split('\n');

  const closePanel = (end: number, line: number) => {
    if (panel) { panel.endOffset = end; panel.endLine = line; }
    panel = null;
  };
  const closePage = (end: number, line: number) => {
    if (page) { page.endOffset = end; page.endLine = line; }
    page = null;
  };

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const start = at;
    at += raw.length + 1;
    const t = raw.replace(/\r$/, '').trim();
    if (!t || t.startsWith('//')) continue;
    let m: RegExpMatchArray | null;

    if ((m = t.match(/^PAGE\b(.*)$/))) {
      closePanel(start, i);
      closePage(start, i);
      const u = m[1].match(UNCUT_RE);
      const rest = u ? m[1].slice(u[0].length) : m[1].replace(/^\s*\d+/, '');
      const title = rest.replace(/^\s*[—–-]+\s*/, '').trim();
      const common = { title, startOffset: start, endOffset: text.length, startLine: i + 1, endLine: lines.length, panels: [], regular: 0, uncutPanels: 0 };
      if (u) {
        uncutPages++;
        page = { ...common, id: `u${uncutPages}`, n: null, uncutIndex: uncutPages, uncut: true, todo: !!u[1] };
      } else {
        regularPages++;
        page = { ...common, id: String(regularPages), n: regularPages, uncutIndex: null, uncut: false, todo: false };
      }
      pages.push(page);
      continue;
    }

    if ((m = t.match(/^PANEL\b(.*)$/))) {
      closePanel(start, i);
      const pg = page as WorkPage | null;
      if (!pg) continue;   // a PANEL before the first PAGE: an error in comic.js; not a panel here
      const u = m[1].match(UNCUT_RE);
      let id: string, uncut: boolean, todo: boolean;
      if (u && !pg.uncut) {
        pg.uncutPanels++;
        id = `${pg.n}.u${pg.uncutPanels}`;
        uncut = true;
        todo = !!u[1];
      } else {
        pg.regular++;
        id = pg.uncut ? `u${pg.uncutIndex}.${pg.regular}` : `${pg.n}.${pg.regular}`;
        uncut = pg.uncut;
        todo = pg.todo || (pg.uncut && !!u?.[1]);
      }
      panel = {
        id, page: pg.id, startOffset: start, endOffset: text.length, line: i + 1, endLine: lines.length,
        cast: [], shot: '', place: null, time: null, ownPlace: false, ownTime: null, firstDescription: '',
        uncut, todo, captionBreak: false, onUncutPage: pg.uncut, lettered: false,
      };
      pg.panels.push(id);
      panels.push(panel);
      continue;
    }

    const p = panel as WorkPanel | null;
    if (!p) continue;   // the script header, or a page's own lines (layout:)
    if ((m = t.match(SPEECH_RE))) {
      if (!p.lettered) {
        p.lettered = true;
        p.captionBreak = m[1] === 'CAPTION' && sceneCaption(m[3]);
      }
      continue;
    }
    if ((m = t.match(KEY_RE)) && NOT_DESCRIPTION.has(m[1].toLowerCase())) {
      const key = m[1].toLowerCase(), val = m[2].trim();
      if (key === 'place') {
        const pl = parsePlace(val);
        p.ownPlace = !!pl.key;
        p.place = pl.key || null;
        p.ownTime = pl.time;
      } else if (key === 'cast') p.cast = castIds(val);
      else if (key === 'shot') p.shot = val;
      continue;
    }
    if (!p.firstDescription) p.firstDescription = shorten(t);
  }

  // the place carries over (lib/script.js): regular panels from the regular panel before them...
  let last: { place: string | null; time: string | null } | null = null;
  for (const p of panels) {
    if (p.uncut) continue;
    if (p.ownPlace) last = { place: p.place, time: p.ownTime };
    p.place = last?.place ?? null;
    p.time = last?.time ?? null;
  }
  // ...and uncut panels from the panel before them in the script, regular or uncut
  last = null;
  for (const p of panels) {
    if (p.uncut) {
      if (p.ownPlace) { p.time = p.ownTime; } else { p.place = last?.place ?? null; p.time = last?.time ?? null; }
    }
    if (p.place) last = { place: p.place, time: p.time };
  }

  const scenes: OutlineScene[] = [];
  let prev: WorkPanel | null = null;
  for (const p of panels) {
    const same = prev && !p.captionBreak && prev.onUncutPage === p.onUncutPage
      && (prev.place ?? '').toLowerCase() === (p.place ?? '').toLowerCase() && prev.time === p.time;
    const scene = scenes[scenes.length - 1];
    if (same && scene) {
      scene.panels.push(p.id);
      scene.endOffset = p.endOffset;
      scene.endLine = p.endLine;
      for (const c of p.cast) if (!scene.cast.includes(c)) scene.cast.push(c);
      scene.uncut &&= p.uncut;
      scene.todo ||= p.todo;
    } else {
      scenes.push({
        id: `s${scenes.length + 1}`, place: p.place, time: p.time, startOffset: p.startOffset, endOffset: p.endOffset,
        startLine: p.line, endLine: p.endLine, panels: [p.id], cast: [...p.cast], uncut: p.uncut, todo: p.todo,
      });
    }
    prev = p;
  }

  const outPanels: OutlinePanel[] = panels.map(({ ownTime, onUncutPage, lettered, ...rest }) => rest);
  const outPages: OutlinePage[] = pages.map(({ regular, uncutPanels, ...rest }) => rest);
  return { pages: outPages, scenes, panels: outPanels, length: text.length };
}

// memoised per text: the Outline panel, the AI popover and the shortcuts all ask for the same text's outline
const cache = new Map<string, Outline>();
const CACHE_SIZE = 4;

export function parseOutline(text: string): Outline {
  const hit = cache.get(text);
  if (hit) return hit;
  let out: Outline;
  try { out = parse(text); } catch { out = { pages: [], scenes: [], panels: [], length: text.length }; }
  cache.set(text, out);
  if (cache.size > CACHE_SIZE) cache.delete(cache.keys().next().value as string);
  return out;
}

const startOf = (e: OutlineEntry) => ('startOffset' in e ? e.startOffset : 0);

/** The entry of `list` (sorted, non-overlapping) whose block holds `offset`; a caret at the very end of the text
    is in the last block when it runs to the end. */
export function entryAt<T extends OutlineEntry>(list: T[], offset: number, length = Infinity): T | null {
  let lo = 0, hi = list.length - 1, found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (startOf(list[mid]) <= offset) { found = mid; lo = mid + 1; } else hi = mid - 1;
  }
  if (found < 0) return null;
  const e = list[found];
  return offset < e.endOffset || (offset === e.endOffset && e.endOffset === length) ? e : null;
}

export function listOf(outline: Outline, kind: OutlineKind): OutlineEntry[] {
  return kind === 'page' ? outline.pages : kind === 'scene' ? outline.scenes : outline.panels;
}

export interface OutlineTarget { kind: OutlineKind; start: number; end: number; entry: OutlineEntry }

/** The block of `kind` around `offset` (an AI rewrite target): the panel, scene or page holding it. On a PAGE line
    or its layout: (no panel there) the panel and scene targets take the page's first panel. null in the script
    header, or on a page without panels for panel/scene. */
export function targetAt(outline: Outline, offset: number, kind: OutlineKind): OutlineTarget | null {
  const wrap = (entry: OutlineEntry | null | undefined): OutlineTarget | null =>
    (entry ? { kind, start: entry.startOffset, end: entry.endOffset, entry } : null);
  const page = entryAt(outline.pages, offset, outline.length);
  if (kind === 'page') return wrap(page);
  let panel = entryAt(outline.panels, offset, outline.length);
  if (!panel && page?.panels.length) panel = outline.panels.find(p => p.id === page.panels[0]) ?? null;
  if (kind === 'panel') return wrap(panel);
  return wrap(entryAt(outline.scenes, offset, outline.length) ?? (panel && entryAt(outline.scenes, panel.startOffset, outline.length)));
}

/** "cafe" → "Cafe", "sand_court" → "Sand court". */
export function prettyPlace(key: string): string {
  const s = key.replace(/_/g, ' ').trim();
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

export const panelRange = (ids: string[]) =>
  (ids.length ? (ids.length === 1 ? ids[0] : `${ids[0]}–${ids[ids.length - 1]}`) : '');

export interface OutlineWords { page: string; uncutPage: string; noPlace: string; panel: string; scene: string }

/** An entry's label: "Page 3 — Practice", "Uncut page 1", "Cafe, morning · 2.1–3.4", "2.3". */
export function entryLabel(kind: OutlineKind, entry: OutlineEntry, w: OutlineWords): string {
  if (kind === 'page') {
    const p = entry as OutlinePage;
    const head = p.uncut ? w.uncutPage.replace('{n}', String(p.uncutIndex)) : w.page.replace('{n}', String(p.n));
    return p.title ? `${head} — ${p.title}` : head;
  }
  if (kind === 'scene') {
    const s = entry as OutlineScene;
    const place = s.place ? prettyPlace(s.place.length > 40 ? `${s.place.slice(0, 39).trimEnd()}…` : s.place) : w.noPlace;
    return `${place}${s.time ? `, ${s.time}` : ''} · ${panelRange(s.panels)}`;
  }
  return (entry as OutlinePanel).id;
}

/** A target's label for the AI popover: "Scene: Cafe, morning · 2.1–3.4", "Panel 2.3", "Page 3 — Practice". */
export function targetLabel(target: OutlineTarget, w: OutlineWords): string {
  const label = entryLabel(target.kind, target.entry, w);
  if (target.kind === 'scene') return `${w.scene}: ${label}`;
  if (target.kind === 'panel') return `${w.panel} ${label}`;
  return label;
}

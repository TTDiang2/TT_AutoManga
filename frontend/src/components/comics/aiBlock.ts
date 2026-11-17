/** The block of a .comic script an AI rewrite works on: the selection, else the PANEL block around the caret
    (from its PANEL line to the line before the next PANEL/PAGE), or its whole PAGE. Offsets are string indices
    (UTF-16 code units), as the server takes them. Works on CRLF text (lines keep their \r). */

import { parseOutline, targetAt, targetLabel, type OutlineKind, type OutlineWords } from './outline';

export type BlockKind = 'selection' | 'panel' | 'scene' | 'page';

export interface AiBlock {
  start: number;
  end: number;
  kind: BlockKind;
  firstLine: number;   // 1-based script lines
  lastLine: number;
  uncut: boolean;      // every line is inside a PAGE uncut / PANEL uncut block (Draft uncut scene is offered)
  todo: boolean;       // it holds an uncut todo marker
  label?: string;      // an outline target's label ("Scene: Cafe, day · 2.1–3.4")
}

const MARKER = /^\s*(PAGE|PANEL)\b/;
const UNCUT = /^\s*(?:PAGE|PANEL)\s+(?:\d+\s+)?uncut\b(\s+todo\b)?/;

interface Span { line: number; end: number; uncut: boolean; todo: boolean }
interface PanelSpan extends Span { page: Span }

/** Pages and panels of the script, as 0-based line spans (end inclusive). */
export function scriptStructure(lines: string[]) {
  const pages: Span[] = [];
  const panels: PanelSpan[] = [];
  lines.forEach((l, i) => {
    const m = l.match(MARKER);
    if (!m) return;
    const u = l.match(UNCUT);
    const open = panels[panels.length - 1];
    if (open && open.end < 0) open.end = i - 1;
    if (m[1] === 'PAGE') {
      if (pages.length) pages[pages.length - 1].end = i - 1;
      pages.push({ line: i, end: -1, uncut: !!u, todo: !!u?.[1] });
    } else if (pages.length) {
      panels.push({ line: i, end: -1, uncut: !!u, todo: !!u?.[1], page: pages[pages.length - 1] });
    }
  });
  if (pages.length) pages[pages.length - 1].end = lines.length - 1;
  const last = panels[panels.length - 1];
  if (last && last.end < 0) last.end = lines.length - 1;
  return { pages, panels };
}

function lineUncut(i: number, pages: Span[], panels: PanelSpan[]) {
  const p = panels.find(p => p.line <= i && i <= p.end);
  if (p) return p.uncut || p.page.uncut;
  const pg = pages.find(pg => pg.line <= i && i <= pg.end);
  return pg ? pg.uncut : false;
}

/** The block for the editor's selection [selStart, selEnd): null when the caret is in the script header (before
    the first PAGE) or nothing is there. page: widen a caret's panel to its whole page. */
export function findBlock(text: string, selStart: number, selEnd: number, page = false): AiBlock | null {
  const lines = text.split('\n');
  const starts: number[] = [];
  let at = 0;
  for (const l of lines) { starts.push(at); at += l.length + 1; }
  const lineAt = (off: number) => {
    let lo = 0, hi = starts.length - 1;
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (starts[mid] <= off) lo = mid; else hi = mid - 1; }
    return lo;
  };
  const offsetOf = (line: number) => (line >= lines.length ? text.length : starts[line]);
  const { pages, panels } = scriptStructure(lines);
  const describe = (start: number, end: number, kind: BlockKind): AiBlock | null => {
    if (end <= start || !text.slice(start, end).trim()) return null;
    const lo = lineAt(start), hi = lineAt(Math.max(start, end - 1));
    let uncut = true, todo = false;
    for (let i = lo; i <= hi; i++) {
      if (!lineUncut(i, pages, panels)) uncut = false;
      if (lines[i].match(UNCUT)?.[1]) todo = true;
    }
    return { start, end, kind, firstLine: lo + 1, lastLine: hi + 1, uncut, todo };
  };

  const a = Math.max(0, Math.min(selStart, selEnd)), b = Math.min(text.length, Math.max(selStart, selEnd));
  if (b > a) return describe(a, b, 'selection');
  const line = lineAt(a);
  const pg = pages.find(p => p.line <= line && line <= p.end);
  if (!pg) return null;   // the script header
  const panel = panels.find(p => p.line <= line && line <= p.end);
  if (panel && !page) return describe(offsetOf(panel.line), offsetOf(panel.end + 1), 'panel');
  return describe(offsetOf(pg.line), offsetOf(pg.end + 1), 'page');
}

export type TargetKind = OutlineKind | 'selection';

/** The block the popover works on: `kind` null = its own detection (the selection, else the panel at the caret, else
    the page); else that outline block around `anchor`. */
export function resolveBlock(text: string, caret: { start: number; end: number }, kind: TargetKind | null, anchor: number, words: OutlineWords): AiBlock | null {
  if (kind === null || kind === 'selection') return findBlock(text, caret.start, caret.end);
  const t = targetAt(parseOutline(text), anchor, kind);
  const b = t && findBlock(text, t.start, t.end);
  return b ? { ...b, kind, label: targetLabel(t, words) } : null;
}

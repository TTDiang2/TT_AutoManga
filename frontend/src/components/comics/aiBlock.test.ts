import { describe, it, expect } from 'vitest';
import { findBlock, resolveBlock } from './aiBlock';
import type { OutlineWords } from './outline';

const SCRIPT = [
  'title: T',            // 1
  '',                    // 2
  'PAGE',                // 3
  'layout: 1-2',         // 4
  '',                    // 5
  'PANEL h=1.2',         // 6
  'cast: kim',           // 7
  'Kim sits.',           // 8
  'KIM: Hi.',            // 9
  '',                    // 10
  'PANEL uncut todo',    // 11
  'cast: kim',           // 12
  '',                    // 13
  'PAGE uncut',          // 14
  'PANEL',               // 15
  'cast: kim',           // 16
  'Kim alone.',          // 17
].join('\n');

const offsetOfLine = (text: string, line: number) => text.split('\n').slice(0, line - 1).reduce((n, l) => n + l.length + 1, 0);
const slice = (text: string, b: { start: number; end: number } | null) => (b ? text.slice(b.start, b.end) : null);

describe('findBlock', () => {
  it('takes a non-empty selection as it is', () => {
    const at = offsetOfLine(SCRIPT, 8);
    const b = findBlock(SCRIPT, at, at + 9);
    expect(b).toMatchObject({ kind: 'selection', firstLine: 8, lastLine: 8, uncut: false });
    expect(slice(SCRIPT, b)).toBe('Kim sits.');
    // a backwards selection too
    expect(findBlock(SCRIPT, at + 9, at)?.start).toBe(at);
  });

  it('takes the PANEL block around the caret, up to the next PANEL', () => {
    const b = findBlock(SCRIPT, offsetOfLine(SCRIPT, 8) + 3, offsetOfLine(SCRIPT, 8) + 3);
    expect(b).toMatchObject({ kind: 'panel', firstLine: 6, lastLine: 10, uncut: false, todo: false });
    expect(slice(SCRIPT, b)).toBe('PANEL h=1.2\ncast: kim\nKim sits.\nKIM: Hi.\n\n');
  });

  it('widens to the whole page on request, and takes the page when the caret is in its header', () => {
    const caret = offsetOfLine(SCRIPT, 7);
    const page = findBlock(SCRIPT, caret, caret, true);
    expect(page).toMatchObject({ kind: 'page', firstLine: 3, lastLine: 13, uncut: false, todo: true });
    const header = findBlock(SCRIPT, offsetOfLine(SCRIPT, 4), offsetOfLine(SCRIPT, 4));
    expect(header).toMatchObject({ kind: 'page', firstLine: 3, lastLine: 13 });
  });

  it('marks uncut panels and pages', () => {
    const panel = findBlock(SCRIPT, offsetOfLine(SCRIPT, 12), offsetOfLine(SCRIPT, 12));
    expect(panel).toMatchObject({ kind: 'panel', firstLine: 11, lastLine: 13, uncut: true, todo: true });
    const onUncutPage = findBlock(SCRIPT, offsetOfLine(SCRIPT, 17), offsetOfLine(SCRIPT, 17));
    expect(onUncutPage).toMatchObject({ kind: 'panel', firstLine: 15, lastLine: 17, uncut: true, todo: false });
    expect(slice(SCRIPT, onUncutPage)).toBe('PANEL\ncast: kim\nKim alone.');   // the last panel runs to the end
    const uncutPage = findBlock(SCRIPT, offsetOfLine(SCRIPT, 14), offsetOfLine(SCRIPT, 14));
    expect(uncutPage).toMatchObject({ kind: 'page', firstLine: 14, lastLine: 17, uncut: true });
  });

  it('returns null in the script header and for a blank selection', () => {
    expect(findBlock(SCRIPT, 2, 2)).toBeNull();
    const blank = offsetOfLine(SCRIPT, 10);
    expect(findBlock(SCRIPT, blank, blank + 1)).toBeNull();
  });

  it('works on CRLF text', () => {
    const crlf = SCRIPT.replace(/\n/g, '\r\n');
    const caret = offsetOfLine(crlf, 8);
    const b = findBlock(crlf, caret, caret);
    expect(b).toMatchObject({ kind: 'panel', firstLine: 6, lastLine: 10 });
    expect(slice(crlf, b)).toBe('PANEL h=1.2\r\ncast: kim\r\nKim sits.\r\nKIM: Hi.\r\n\r\n');
    expect(findBlock(crlf, offsetOfLine(crlf, 12), offsetOfLine(crlf, 12))).toMatchObject({ uncut: true, todo: true });
  });
});

const WORDS: OutlineWords = { page: 'Page {n}', uncutPage: 'Uncut page {n}', noPlace: 'No place', panel: 'Panel', scene: 'Scene' };

describe('resolveBlock (the popover target and its "change target")', () => {
  const caretAt = (line: number) => { const o = offsetOfLine(SCRIPT, line); return { start: o, end: o }; };

  it('keeps the popover\'s own detection without a kind', () => {
    expect(resolveBlock(SCRIPT, caretAt(8), null, 0, WORDS)).toEqual(findBlock(SCRIPT, offsetOfLine(SCRIPT, 8), offsetOfLine(SCRIPT, 8)));
    const sel = { start: offsetOfLine(SCRIPT, 8), end: offsetOfLine(SCRIPT, 9) };
    expect(resolveBlock(SCRIPT, sel, 'selection', sel.start, WORDS)).toMatchObject({ kind: 'selection', firstLine: 8, lastLine: 8 });
  });

  it('re-targets the panel, scene and page around the same anchor, with labels and uncut flags', () => {
    const caret = caretAt(8), anchor = caret.start;
    const panel = resolveBlock(SCRIPT, caret, 'panel', anchor, WORDS);
    expect(panel).toMatchObject({ kind: 'panel', firstLine: 6, lastLine: 10, label: 'Panel 1.1', uncut: false });
    const scene = resolveBlock(SCRIPT, caret, 'scene', anchor, WORDS);
    // 1.1 and 1.u1 share no place (none set): one scene of the regular page; the uncut page is a scene of its own
    expect(scene).toMatchObject({ kind: 'scene', firstLine: 6, lastLine: 13, label: 'Scene: No place · 1.1–1.u1', todo: true });
    const page = resolveBlock(SCRIPT, caret, 'page', anchor, WORDS);
    expect(page).toMatchObject({ kind: 'page', firstLine: 3, lastLine: 13, label: 'Page 1' });
    const uncut = resolveBlock(SCRIPT, caretAt(16), 'scene', offsetOfLine(SCRIPT, 16), WORDS);
    expect(uncut).toMatchObject({ firstLine: 15, lastLine: 17, uncut: true, label: 'Scene: No place · u1.1' });
  });

  it('finds the target again after an edit above it', () => {
    const edited = 'title: T\n// a new comment line\n' + SCRIPT.slice('title: T\n'.length);
    const anchor = offsetOfLine(edited, 9);   // Kim sits., one line further down now
    const b = resolveBlock(edited, { start: anchor, end: anchor }, 'panel', anchor, WORDS)!;
    expect(edited.slice(b.start, b.end).startsWith('PANEL h=1.2\n')).toBe(true);
  });

  it('is null in the script header', () => {
    for (const k of ['panel', 'scene', 'page'] as const) expect(resolveBlock(SCRIPT, caretAt(1), k, 0, WORDS)).toBeNull();
  });
});

import { describe, it, expect } from 'vitest';
import { findBlock } from './aiBlock';

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

import { describe, it, expect } from 'vitest';
import { renderPageToImage, wrapText } from './pageRenderer';
import type { ComposerPage } from '../../types';

// deterministic measureText: every char is 10px wide
function fakeCtx() {
  return {
    measureText: (t: string) => ({ width: t.length * 10 }),
  } as unknown as CanvasRenderingContext2D;
}

describe('wrapText', () => {
  it('breaks a line once it exceeds maxWidth', () => {
    // 6 chars fit in 60px, the 7th starts a new line
    expect(wrapText(fakeCtx(), 'abcdefgh', 60)).toEqual(['abcdef', 'gh']);
  });

  it('keeps explicit newlines as separate lines', () => {
    expect(wrapText(fakeCtx(), 'ab\ncd', 100)).toEqual(['ab', 'cd']);
  });

  it('preserves empty lines', () => {
    expect(wrapText(fakeCtx(), 'a\n\nb', 100)).toEqual(['a', '', 'b']);
  });

  it('never produces lines wider than maxWidth (single chars excluded)', () => {
    const lines = wrapText(fakeCtx(), 'abcdef'.repeat(4), 25);
    expect(lines.every(l => l.length <= 3)).toBe(true);
    expect(lines.join('')).toBe('abcdef'.repeat(4));
  });

  it('puts a first char that is already too wide on its own line', () => {
    expect(wrapText(fakeCtx(), 'abcd', 5)).toEqual(['a', 'b', 'c', 'd']);
  });
});

describe('renderPageToImage', () => {
  it('resolves for a page with only text and bubble elements', async () => {
    const page: ComposerPage = {
      id: 'p1',
      name: 'test',
      templateId: '',
      width: 600,
      height: 900,
      order: 0,
      elements: [
        { id: 't1', type: 'text', x: 10, y: 10, width: 50, height: 10,
          rotation: 0, zIndex: 0, locked: false, visible: true,
          content: 'hello', fontSize: 14, direction: 'horizontal' } as never,
        { id: 'b1', type: 'bubble', x: 10, y: 40, width: 40, height: 20,
          rotation: 0, zIndex: 1, locked: false, visible: true,
          bubbleType: 'speech', text: 'hi', tailPosition: 'top',
          direction: 'vertical', fontSize: 14 } as never,
      ],
    };
    // under jsdom without the canvas package the context is null and the
    // renderer resolves ''; with a real canvas it resolves a data URL —
    // the contract is "resolves to a string, never rejects"
    const out = await renderPageToImage(page);
    expect(typeof out).toBe('string');
  });
});

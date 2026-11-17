import { beforeEach, describe, expect, it } from 'vitest';
import { effectiveRating, isRevealed, matureNames, resetRevealed, revealMature } from './rating';

describe('effectiveRating', () => {
  it('uses the project rating, else the default', () => {
    expect(effectiveRating({ contentRating: 'mature' }, 'sfw')).toBe('mature');
    expect(effectiveRating({ contentRating: 'sfw' }, 'mature')).toBe('sfw');
    expect(effectiveRating({}, 'mature')).toBe('mature');
    expect(effectiveRating(undefined, 'sfw')).toBe('sfw');
    expect(effectiveRating({ contentRating: 'xxx' }, 'sfw')).toBe('sfw');
  });
});

describe('matureNames', () => {
  it('lists the mature episodes', () => {
    expect(matureNames([{ name: 'A', contentRating: 'mature' }, { name: 'B', contentRating: 'sfw' }, { name: 'C' }]))
      .toEqual(['A']);
  });
});

describe('revealMature', () => {
  beforeEach(() => resetRevealed());
  it('reveals per session', () => {
    expect(isRevealed('p1')).toBe(false);
    revealMature('p1');
    expect(isRevealed('p1')).toBe(true);
    expect(isRevealed('p2')).toBe(false);
    expect(JSON.parse(window.sessionStorage.getItem('automanga.revealedMature') || '[]')).toEqual(['p1']);
  });
});

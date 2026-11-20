import { describe, it, expect } from 'vitest';
import { addEpisodes, clampScale, episodeTitle, exportPercent, moveItem } from './collectionUtils';

describe('moveItem', () => {
  it('moves up and down without mutating the input', () => {
    const ids = ['a', 'b', 'c', 'd'];
    expect(moveItem(ids, 2, 1)).toEqual(['a', 'c', 'b', 'd']);
    expect(moveItem(ids, 0, 3)).toEqual(['b', 'c', 'd', 'a']);
    expect(ids).toEqual(['a', 'b', 'c', 'd']);
  });

  it('ignores out-of-range and no-op moves', () => {
    expect(moveItem(['a', 'b'], 0, -1)).toEqual(['a', 'b']);
    expect(moveItem(['a', 'b'], 1, 2)).toEqual(['a', 'b']);
    expect(moveItem(['a', 'b'], 1, 1)).toEqual(['a', 'b']);
  });
});

describe('addEpisodes', () => {
  it('appends new ids in order and skips ones already present', () => {
    expect(addEpisodes(['a', 'b'], ['c', 'a', 'd', 'c'])).toEqual(['a', 'b', 'c', 'd']);
  });
});

describe('episodeTitle', () => {
  it('strips the collection title from a "<Title> — <Subtitle>" name', () => {
    expect(episodeTitle('Jade & Haile', 'Jade & Haile — Episode 1 — The Rainy Gym'))
      .toBe('Episode 1 — The Rainy Gym');
    expect(episodeTitle('The Space Between Us', 'The Space Between Us — Part One')).toBe('Part One');
    expect(episodeTitle('Saga', 'Saga - Ep. 3')).toBe('Ep. 3');
  });

  it('keeps names of another series or without a separator', () => {
    expect(episodeTitle('Jade & Haile', 'Rooftop Chase')).toBe('Rooftop Chase');
    expect(episodeTitle('Mara', 'Spider-Gwen - The Fall')).toBe('Spider-Gwen - The Fall');
    expect(episodeTitle('Sketches', 'Sketches')).toBe('Sketches');
  });
});

describe('export helpers', () => {
  it('computes a bounded percentage', () => {
    expect(exportPercent(null)).toBe(0);
    expect(exportPercent({ done: 0, total: 0 })).toBe(0);
    expect(exportPercent({ done: 13, total: 40 })).toBe(33);
    expect(exportPercent({ done: 41, total: 40 })).toBe(100);
  });

  it('clamps the scale like the backend', () => {
    expect(clampScale(0.1)).toBe(0.5);
    expect(clampScale(12)).toBe(8);
    expect(clampScale(Number.NaN)).toBe(2);
    expect(clampScale(3)).toBe(3);
  });
});

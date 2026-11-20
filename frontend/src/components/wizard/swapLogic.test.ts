import { describe, expect, it } from 'vitest';
import { storyNames, swapNames } from './swapLogic';

describe('storyNames', () => {
  it('finds recurring names and speakers, not sentence starters', () => {
    const story = `The rain fell on the bridge. Anna waited for Ben.
Later, Ben arrived late. The lanterns swayed and Anna smiled.
BEN: Sorry!
Kai: Who are you?`;
    const names = storyNames(story);
    expect(names).toEqual(expect.arrayContaining(['Anna', 'Ben', 'Kai']));
    expect(names).not.toContain('The');
    expect(names).not.toContain('Later');
  });
  it('reads CJK speakers', () => {
    expect(storyNames('小雪：快跑！\n李白：等等我。\n小雪：来不及了')).toEqual(['小雪', '李白']);
  });
  it('skips shot labels, directions, pronoun contractions; merges possessives', () => {
    const story = `ACT ONE: THE SLOW BURN
Page 1 — Establishing Shots
Panel 1 (Wide): Exterior of a gym. Still dark outside.
Panel 2 (Medium): Inside. Marcus, 48, sits on a bike. He's tired. Marcus's towel slips.
Panel 3 (Close-Up): Elena glances Left, then Right. She's smiling. I've seen Elena here.
Panel 4 (Wide): Frame Left, Marcus waves. Elena's bike is Right of his.`;
    expect(storyNames(story)).toEqual(['Marcus', 'Elena']);
  });
  it('keeps a one-character CJK speaker', () => {
    expect(storyNames('雪：快跑！\n雪：等等')).toEqual(['雪']);
  });
  it('ignores a capitalised word seen only once', () => {
    expect(storyNames('Once upon a time, Mira walked home.')).toEqual([]);
  });
});

describe('swapNames', () => {
  it('replaces whole words only, keeping capitals', () => {
    expect(swapNames('Anna met Annabel. ANNA: hi! anna\'s hat', { Anna: 'Jade' }))
      .toBe('Jade met Annabel. JADE: hi! Jade\'s hat');
  });
  it('swaps two people at once', () => {
    expect(swapNames('Anna hugs Ben.', { Anna: 'Ben', Ben: 'Anna' })).toBe('Ben hugs Anna.');
  });
  it('replaces CJK names anywhere', () => {
    expect(swapNames('小雪：快跑！小雪跑了', { 小雪: '玉儿' })).toBe('玉儿：快跑！玉儿跑了');
  });
  it('leaves the text alone without swaps', () => {
    expect(swapNames('Anna', { Anna: '', Ben: 'Kai' })).toBe('Anna');
  });
});

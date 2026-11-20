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

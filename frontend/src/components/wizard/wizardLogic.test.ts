import { describe, expect, it } from 'vitest';
import {
  DEFAULT_STATE, castFromPanels, emptyScenes, guessPromptFormat, loadState,
  maxReachableStep, movePanel, newPanel, parseNames, prefersVerticalBubbles, promptForPanel,
} from './wizardLogic';
import type { Panel } from '../../types';

const panel = (over: Partial<Panel> = {}): Panel => ({
  id: 'panel_1', order: 0, scene: 'a street', characters: [], dialogue: '', prompt: {}, ...over,
});

describe('loadState', () => {
  it('falls back to defaults on missing or broken data', () => {
    expect(loadState(null)).toEqual(DEFAULT_STATE);
    expect(loadState('{nope')).toEqual(DEFAULT_STATE);
  });
  it('sanitises bad values', () => {
    const s = loadState(JSON.stringify({ step: 'bogus', reading: 'x', panelsPerPage: 99, detailLevel: -3, projectId: 5 }));
    expect(s.step).toBe('story');
    expect(s.reading).toBe('rtl');
    expect(s.panelsPerPage).toBe(8);
    expect(s.detailLevel).toBe(1);
    expect(s.projectId).toBeNull();
  });
  it('keeps valid values', () => {
    const s = loadState(JSON.stringify({ step: 'art', projectId: 'abc', reading: 'ltr', promptFormat: 'prose' }));
    expect(s).toMatchObject({ step: 'art', projectId: 'abc', reading: 'ltr', promptFormat: 'prose' });
  });
});

describe('maxReachableStep', () => {
  it('unlocks steps as the project fills up', () => {
    expect(maxReachableStep({ hasProject: false, panels: 0, panelsWithImage: 0, pages: 0 })).toBe(0);
    expect(maxReachableStep({ hasProject: true, panels: 0, panelsWithImage: 0, pages: 0 })).toBe(1);
    expect(maxReachableStep({ hasProject: true, panels: 3, panelsWithImage: 0, pages: 0 })).toBe(3);
    expect(maxReachableStep({ hasProject: true, panels: 3, panelsWithImage: 1, pages: 0 })).toBe(4);
    expect(maxReachableStep({ hasProject: true, panels: 3, panelsWithImage: 3, pages: 2 })).toBe(5);
  });
});

describe('names', () => {
  it('parses comma lists with CJK separators and dedupes', () => {
    expect(parseNames('Anna, Ben ,, anna，雪、 ')).toEqual(['Anna', 'Ben', '雪']);
  });
  it('collects the cast in first-appearance order', () => {
    expect(castFromPanels([{ characters: ['Yuki'] }, { characters: ['Ren', 'yuki'] }])).toEqual(['Yuki', 'Ren']);
  });
});

describe('promptForPanel', () => {
  it('uses the enhanced prompt for the matching format, else the scene', () => {
    const p = panel({ prompt: { tags: ['1girl', ' rain'], turbo: 'A girl in the rain' } });
    expect(promptForPanel(p, 'danbooru')).toBe('1girl, rain');
    expect(promptForPanel(p, 'prose')).toBe('A girl in the rain');
    expect(promptForPanel(panel({ prompt: { tags: ['  '] } }), 'danbooru')).toBe('a street');
  });
  it('guesses the format from the model name', () => {
    expect(guessPromptFormat('qwen_image_2.1_int8')).toBe('prose');
    expect(guessPromptFormat('waiIllustriousSDXL_v140')).toBe('danbooru');
  });
});

describe('panel list helpers', () => {
  it('finds empty scenes', () => {
    expect(emptyScenes([panel(), panel({ scene: ' ' }), panel({ scene: '' })])).toEqual([2, 3]);
  });
  it('picks a free id', () => {
    expect(newPanel([{ id: 'panel_1' }, { id: 'panel_3' }]).id).toBe('panel_4');
    expect(newPanel([{ id: 'panel_2' }]).id).toBe('panel_3');
    expect(newPanel([{ id: 'x' }, { id: 'panel_2' }]).id).toBe('panel_3');
  });
  it('moves within bounds only', () => {
    expect(movePanel([1, 2, 3], 0, 2)).toEqual([2, 3, 1]);
    expect(movePanel([1, 2, 3], 0, -1)).toEqual([1, 2, 3]);
  });
});

describe('prefersVerticalBubbles', () => {
  it('is vertical for CJK dialogue only', () => {
    expect(prefersVerticalBubbles([{ dialogue: '雪：别过来！' }])).toBe(true);
    expect(prefersVerticalBubbles([{ dialogue: 'ユキ：待って！' }, { dialogue: 'OK' }])).toBe(true);
    expect(prefersVerticalBubbles([{ dialogue: 'Yuki: Get away from me!' }])).toBe(false);
    expect(prefersVerticalBubbles([{ dialogue: '' }])).toBe(false);
  });
});

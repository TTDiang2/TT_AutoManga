import { describe, expect, it } from 'vitest';
import { flattenTips, placeTip, withId } from './tooltipLogic';
import { tips } from '../../i18n/tips';

const vp = { width: 1000, height: 700 };
const tip = { width: 200, height: 40 };

describe('placeTip', () => {
  it('goes above, centred on the element', () => {
    expect(placeTip({ top: 300, left: 400, width: 100, height: 30 }, tip, vp)).toEqual({ top: 252, left: 350, side: 'top' });
  });
  it('goes below when there is no room above', () => {
    expect(placeTip({ top: 10, left: 400, width: 100, height: 30 }, tip, vp)).toMatchObject({ top: 48, side: 'bottom' });
  });
  it('stays inside the viewport at the edges', () => {
    expect(placeTip({ top: 300, left: 0, width: 20, height: 20 }, tip, vp).left).toBe(8);
    expect(placeTip({ top: 300, left: 990, width: 10, height: 20 }, tip, vp).left).toBe(792);
    expect(placeTip({ top: 0, left: 400, width: 100, height: 700 }, tip, vp).top).toBe(652);
  });
});

describe('withId', () => {
  it('adds and removes one id, keeping the others', () => {
    expect(withId(null, 't', true)).toBe('t');
    expect(withId('a t b', 't', true)).toBe('a b t');
    expect(withId('a t', 't', false)).toBe('a');
    expect(withId('', 't', false)).toBe('');
  });
});

describe('tip text', () => {
  it('has the same non-empty keys in every language', () => {
    const en = flattenTips(tips.en);
    const zh = flattenTips(tips.zh);
    expect(Object.keys(zh).sort()).toEqual(Object.keys(en).sort());
    for (const [k, v] of Object.entries({ ...en, ...zh })) {
      expect(typeof v === 'string' && v.trim().length > 0, k).toBe(true);
    }
  });
});

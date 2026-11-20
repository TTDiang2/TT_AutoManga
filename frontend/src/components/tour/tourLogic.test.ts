import { describe, expect, it } from 'vitest';
import { TOURS, hasTour, nextStep, parseSeen, placePopover, spotlightRect } from './tourLogic';
import { translations } from '../../i18n';

const vp = { width: 1280, height: 800 };
const pop = { width: 320, height: 180 };

describe('placePopover', () => {
  it('centres when there is no target', () => {
    expect(placePopover(null, pop, vp)).toEqual({ top: 310, left: 480, placement: 'center' });
  });
  it('prefers below, then above, then the sides', () => {
    expect(placePopover({ top: 100, left: 100, width: 200, height: 40 }, pop, vp).placement).toBe('bottom');
    expect(placePopover({ top: 600, left: 100, width: 200, height: 40 }, pop, vp).placement).toBe('top');
    expect(placePopover({ top: 100, left: 100, width: 300, height: 650 }, pop, vp).placement).toBe('right');
    expect(placePopover({ top: 100, left: 900, width: 300, height: 650 }, pop, vp).placement).toBe('left');
  });
  it('lays over a target that fills the screen, inside the viewport', () => {
    const p = placePopover({ top: 0, left: 0, width: 1280, height: 800 }, pop, vp);
    expect(p.placement).toBe('over');
    expect(p.top + pop.height).toBeLessThanOrEqual(vp.height);
  });
  it('keeps the popover inside the viewport horizontally', () => {
    const p = placePopover({ top: 100, left: 1200, width: 60, height: 30 }, pop, vp);
    expect(p.left + pop.width).toBeLessThanOrEqual(vp.width);
    expect(placePopover({ top: 100, left: 0, width: 20, height: 30 }, pop, vp).left).toBeGreaterThan(0);
  });
});

describe('spotlightRect', () => {
  it('pads the target and clips it to the viewport', () => {
    expect(spotlightRect({ top: 100, left: 100, width: 50, height: 20 }, vp)).toEqual({ top: 94, left: 94, width: 62, height: 32 });
    expect(spotlightRect({ top: -50, left: 1250, width: 100, height: 100 }, vp)).toEqual({ top: 0, left: 1244, width: 36, height: 56 });
  });
});

describe('nextStep', () => {
  const steps = [{ key: 'a' }, { key: 'b', target: 'x' }, { key: 'c', target: 'y' }, { key: 'd' }];
  it('skips steps whose target is missing', () => {
    expect(nextStep(steps, 0, 1, t => t === 'y')).toBe(2);
    expect(nextStep(steps, 0, 1, () => false)).toBe(3);
    expect(nextStep(steps, 3, -1, () => false)).toBe(0);
    expect(nextStep(steps, 3, 1, () => true)).toBe(-1);
  });
});

describe('seen tours', () => {
  it('parses stored lists and ignores junk', () => {
    expect([...parseSeen('["storyboard",3]')]).toEqual(['storyboard']);
    expect(parseSeen('{').size).toBe(0);
    expect(parseSeen(null).size).toBe(0);
  });
  it('has a tour for every tab', () => {
    expect(hasTour('wizard')).toBe(true);
    expect(hasTour('composer')).toBe(true);
  });
});

describe('tour text', () => {
  it('has a title and body for every step in every language', () => {
    for (const lang of Object.keys(translations) as (keyof typeof translations)[]) {
      const steps = translations[lang].tour.steps as Record<string, Record<string, { title: string; body: string }>>;
      for (const [tab, list] of Object.entries(TOURS)) {
        for (const s of list) {
          expect(steps[tab]?.[s.key]?.title, `${lang}.${tab}.${s.key}`).toBeTruthy();
          expect(steps[tab]?.[s.key]?.body, `${lang}.${tab}.${s.key}`).toBeTruthy();
        }
      }
    }
  });
});

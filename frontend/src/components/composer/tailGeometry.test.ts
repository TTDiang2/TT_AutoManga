import { describe, it, expect } from 'vitest';
import { tailGeometry, parseStars, type Pt } from './tailGeometry';

// the same fixture pytest checks backend/render/tails.py against
import fixtureJson from '../../../../backend/tests/fixtures/tail_cases.json';

interface TailCase {
  bubbleType: string; w: number; h: number; tip: number[]; inset: number;
  expect: null | { kind: 'wedge'; p1: number[]; p2: number[]; ctrl: number[]; tip: number[] }
    | { kind: 'circles'; circles: number[][] };
}
const cases = (fixtureJson as unknown as { cases: TailCase[] }).cases;

const close = (a: number[], b: number[]) =>
  a.forEach((v, i) => expect(Math.abs(v - b[i])).toBeLessThan(1e-4));

describe('tailGeometry matches the shared fixture', () => {
  for (const c of cases) {
    it(`${c.bubbleType} ${c.w}x${c.h} tip ${c.tip}`, () => {
      const g = tailGeometry(c.bubbleType, c.w, c.h, c.tip as Pt, c.inset);
      const exp = c.expect;
      if (exp === null) { expect(g).toBeNull(); return; }
      expect(g?.kind).toBe(exp.kind);
      if (g?.kind === 'wedge' && exp.kind === 'wedge') {
        for (const k of ['p1', 'p2', 'ctrl', 'tip'] as const) close(g[k], exp[k]);
      } else if (g?.kind === 'circles' && exp.kind === 'circles') {
        expect(g.circles.length).toBe(exp.circles.length);
        g.circles.forEach((circle, i) => close(circle, exp.circles[i]));
      }
    });
  }
});

describe('parseStars', () => {
  it('flags *x* as emphasis and drops the stars', () => {
    const { plain, em } = parseStars('a *bc* d');
    expect(plain).toBe('a bc d');
    expect(em).toEqual([false, false, true, true, false, false]);
  });
  it('keeps an unpaired star literal', () => {
    expect(parseStars('5 * 3').plain).toBe('5 * 3');
  });
});

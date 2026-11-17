import { describe, it, expect } from 'vitest';
import { clampInt } from './clampInt';

describe('clampInt', () => {
  it('keeps values in range and rounds', () => {
    expect(clampInt('1500', 10, 10000, 1500)).toBe(1500);
    expect(clampInt('12.6', 1, 64, 24)).toBe(13);
  });
  it('clamps to the bounds', () => {
    expect(clampInt('1', 10, 10000, 1500)).toBe(10);
    expect(clampInt('99999', 10, 10000, 1500)).toBe(10000);
    expect(clampInt('-3', 1, 64, 24)).toBe(1);
  });
  it('falls back on empty or non-numeric text', () => {
    expect(clampInt('', 10, 10000, 1500)).toBe(1500);
    expect(clampInt('  ', 1, 64, 24)).toBe(24);
    expect(clampInt('abc', 1, 64, 24)).toBe(24);
  });
});

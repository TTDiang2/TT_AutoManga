import { describe, expect, it } from 'vitest';
import { parseAge } from './age';

describe('parseAge', () => {
  it('reads empty as unknown', () => {
    expect(parseAge('')).toBeNull();
    expect(parseAge('  ')).toBeNull();
  });
  it('reads whole numbers 0-120', () => {
    expect(parseAge('0')).toBe(0);
    expect(parseAge(' 34 ')).toBe(34);
    expect(parseAge('120')).toBe(120);
  });
  it('rejects anything else', () => {
    for (const s of ['121', '-3', '17.5', 'adult', '1e2', '4000']) expect(parseAge(s)).toBeUndefined();
  });
});

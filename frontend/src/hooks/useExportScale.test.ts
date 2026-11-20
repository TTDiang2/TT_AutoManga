import { describe, expect, it } from 'vitest';
import { scaleForQuality } from './useExportScale';

describe('scaleForQuality', () => {
  it('maps each quality to its render scale', () => {
    expect(scaleForQuality('standard')).toBe(1);
    expect(scaleForQuality('high')).toBe(2);
    expect(scaleForQuality('print')).toBe(4);
  });
  it('falls back to high (2×) for unknown or missing values', () => {
    expect(scaleForQuality(undefined)).toBe(2);
    expect(scaleForQuality('')).toBe(2);
    expect(scaleForQuality('ultra')).toBe(2);
  });
});

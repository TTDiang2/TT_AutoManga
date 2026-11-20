import { describe, expect, it } from 'vitest';
import { IDLE_MS, RETRY_DELAYS, autosaveDelay, maxWaitMs } from './autosave';

describe('autosaveDelay', () => {
  const base = { failures: 0, dirtySince: 1000, maxWaitMs: 60_000 };
  it('saves IDLE_MS after the last edit while the oldest edit is young', () => {
    expect(autosaveDelay({ ...base, now: 1000 })).toBe(IDLE_MS);
    expect(autosaveDelay({ ...base, now: 50_000 })).toBe(IDLE_MS);
  });
  it('saves sooner when the oldest unsaved edit nears the limit', () => {
    expect(autosaveDelay({ ...base, now: 60_000 })).toBe(1000);
    expect(autosaveDelay({ ...base, now: 61_000 })).toBe(0);
    expect(autosaveDelay({ ...base, now: 90_000 })).toBe(0);
  });
  it('uses the retry backoff after failed saves', () => {
    expect(autosaveDelay({ ...base, now: 90_000, failures: 1 })).toBe(RETRY_DELAYS[0]);
    expect(autosaveDelay({ ...base, now: 1000, failures: 9 })).toBe(RETRY_DELAYS[RETRY_DELAYS.length - 1]);
  });
});

describe('maxWaitMs', () => {
  it('converts seconds and keeps the 30–600 s range', () => {
    expect(maxWaitMs(60)).toBe(60_000);
    expect(maxWaitMs(5)).toBe(30_000);
    expect(maxWaitMs(9999)).toBe(600_000);
    expect(maxWaitMs(undefined)).toBe(60_000);
    expect(maxWaitMs(NaN)).toBe(60_000);
  });
});

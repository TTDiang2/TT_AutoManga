/** When the Composer's autosave fires. */

export const IDLE_MS = 2000;                       // save this long after the last edit
export const RETRY_DELAYS = [5000, 15000, 60000];  // backoff after failed saves

/**
 * Milliseconds until the next autosave. Normally IDLE_MS after the last edit,
 * but never later than `maxWaitMs` after the oldest unsaved edit (Settings →
 * Auto-save: "save at least every N seconds"), so editing without a pause
 * still saves. After failed saves the retry backoff applies instead.
 */
export function autosaveDelay(opts: { failures: number; dirtySince: number; now: number; maxWaitMs: number }): number {
  const { failures, dirtySince, now, maxWaitMs } = opts;
  if (failures > 0) return RETRY_DELAYS[Math.min(failures, RETRY_DELAYS.length) - 1];
  const left = dirtySince + maxWaitMs - now;
  return Math.max(0, Math.min(IDLE_MS, left));
}

/** Settings value (seconds) → milliseconds, kept within the field's 30–600 s. */
export function maxWaitMs(seconds: number | undefined | null): number {
  const s = Number.isFinite(seconds) ? (seconds as number) : 60;
  return Math.min(600, Math.max(30, s)) * 1000;
}

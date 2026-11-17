/** A number box's text as an integer in [min, max]; empty or not a number gives `fallback`.
    Applied on blur and on submit, not per keystroke (typing "1500" must pass through "1"). */
export function clampInt(text: string, min: number, max: number, fallback: number): number {
  const n = Math.round(Number(text));
  if (text.trim() === '' || !Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, n));
}

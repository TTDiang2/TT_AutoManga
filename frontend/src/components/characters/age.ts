/** A character's age field: "" = unknown (null); a whole number 0-120; anything else is invalid (undefined). */
export function parseAge(text: string): number | null | undefined {
  const t = text.trim();
  if (!t) return null;
  if (!/^\d{1,3}$/.test(t)) return undefined;
  const n = Number(t);
  return n <= 120 ? n : undefined;
}

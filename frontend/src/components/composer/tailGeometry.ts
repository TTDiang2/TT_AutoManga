// Pointed bubble tails (`tailTip`) — a line-for-line port of
// backend/render/tails.py. Both are checked against
// backend/tests/fixtures/tail_cases.json (tailGeometry.test.ts / pytest),
// so change the two together and regenerate the fixture.
//
// Coordinates are element-local pixels, unrotated; the tip may lie outside
// the box. The root is two points on the body ellipse at
// atan2(...) ± TAIL_SPREAD, pulled inside it so the body hides the seam.

export const TAIL_SPREAD = 0.22;
export const ROOT_K = 0.94;
export const ROOT_K_SHOUT = 0.72;          // inside the star's 0.78 inner radius
export const THOUGHT_R = [0.16, 0.11, 0.07];  // × min(rx, ry), base → tip
export const CURVE_STEPS = 12;

export type Pt = [number, number];
export type TailGeometry =
  | { kind: 'wedge'; p1: Pt; p2: Pt; ctrl: Pt; tip: Pt }
  | { kind: 'circles'; circles: [number, number, number][] };

export function tailGeometry(
  bubbleType: string, w: number, h: number, tip: Pt, inset: number,
): TailGeometry | null {
  if (bubbleType === 'narration') return null;
  const cx = w / 2, cy = h / 2;
  const rx = Math.max(1, w / 2 - inset), ry = Math.max(1, h / 2 - inset);
  const [tx, ty] = tip;
  const nx = (tx - cx) / rx, ny = (ty - cy) / ry;
  if (nx * nx + ny * ny <= 1) return null;
  const t = Math.atan2(ny, nx);
  const bx = cx + rx * Math.cos(t), by = cy + ry * Math.sin(t);
  if (bubbleType === 'thought') {
    const s = Math.min(rx, ry);
    return {
      kind: 'circles',
      circles: THOUGHT_R.map((f, i) => [
        bx + (tx - bx) * (i + 1) / 3, by + (ty - by) * (i + 1) / 3, Math.max(1.5, s * f),
      ] as [number, number, number]),
    };
  }
  const k = bubbleType === 'shout' ? ROOT_K_SHOUT : ROOT_K;
  return {
    kind: 'wedge',
    p1: [cx + rx * k * Math.cos(t - TAIL_SPREAD), cy + ry * k * Math.sin(t - TAIL_SPREAD)],
    p2: [cx + rx * k * Math.cos(t + TAIL_SPREAD), cy + ry * k * Math.sin(t + TAIL_SPREAD)],
    ctrl: [bx + (tx - bx) * 0.5, by + (ty - by) * 0.5],
    tip: [tx, ty],
  };
}

/** SVG / Path2D path: p1 →(quadratic via ctrl)→ tip → p2, open (closed=false) for the edge stroke. */
export function wedgePath(g: Extract<TailGeometry, { kind: 'wedge' }>, closed: boolean): string {
  const f = (p: Pt) => `${p[0].toFixed(2)},${p[1].toFixed(2)}`;
  return `M${f(g.p1)} Q${f(g.ctrl)} ${f(g.tip)} L${f(g.p2)}${closed ? ' Z' : ''}`;
}

/** The body inset the server uses (bubbles.py: max(1, round(2 * scale))). */
export const SERVER_INSET = 2;

/** `*x*` → plain text and per-character emphasis flags (bubbles.py parse_stars). */
export function parseStars(text: string): { plain: string; em: boolean[] } {
  let plain = '';
  const em: boolean[] = [];
  let i = 0;
  for (const m of text.matchAll(/\*([^*\n]+)\*/g)) {
    const before = text.slice(i, m.index);
    plain += before;
    for (const _ of before) em.push(false);
    plain += m[1];
    for (const _ of m[1]) em.push(true);
    i = (m.index ?? 0) + m[0].length;
  }
  const rest = text.slice(i);
  plain += rest;
  for (const _ of rest) em.push(false);
  return { plain, em };
}

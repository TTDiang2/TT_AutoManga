/** Where a panel is in its .comic script, as comic.js --plan reports it (1-based lines). */
export interface PanelLines {
  line: number;             // the PANEL line
  seedLine: number | null;  // a "seed: N" key line in the panel, if it has one
}

const SEED_KEY = /^\s*seed\s*:/i;
const PANEL_HEAD = /^\s*PANEL\b/;
const BLOCK_HEAD = /^\s*(PANEL|PAGE)\b/;

/** Pin a panel's seed in the script text: rewrite its "seed:" line if it has one, else set (or replace)
    seed=N on its PANEL line. Only lines of this panel are touched: from its PANEL line up to the next
    PANEL or PAGE line (a "seed:" outside it, e.g. the script's base seed, never). Throws when the PANEL
    line no longer matches (the text changed since the plan). */
export function pinSeed(text: string, panel: PanelLines, seed: number): string {
  const lines = text.split('\n');   // a "\r" stays on its line, so CRLF scripts keep their endings
  const head = lines[panel.line - 1];
  if (head === undefined || !PANEL_HEAD.test(head)) throw new Error(`line ${panel.line} is not a PANEL line any more`);
  // the panel's body: 0-based indexes after the PANEL line, before the next block
  let end = panel.line;
  while (end < lines.length && !BLOCK_HEAD.test(lines[end])) end++;
  const inPanel = (i: number) => i >= panel.line && i < end;

  // the plan's seed line if it is still a seed line of this panel, else one found in the panel
  let keyIdx = panel.seedLine != null ? panel.seedLine - 1 : -1;
  if (!(inPanel(keyIdx) && SEED_KEY.test(lines[keyIdx]))) {
    keyIdx = -1;
    for (let i = panel.line; i < end; i++) if (SEED_KEY.test(lines[i])) { keyIdx = i; break; }
  }
  if (keyIdx >= 0) {
    lines[keyIdx] = lines[keyIdx].replace(/^(\s*seed\s*:\s*)[^\r]*/i, `$1${seed}`);
    return lines.join('\n');
  }

  const cr = head.endsWith('\r') ? '\r' : '';
  const body = head.slice(0, head.length - cr.length);
  lines[panel.line - 1] = (/(^|\s)seed=\S*/.test(body)
    ? body.replace(/(^|\s)seed=\S*/, `$1seed=${seed}`)
    : `${body.replace(/\s+$/, '')} seed=${seed}`) + cr;
  return lines.join('\n');
}

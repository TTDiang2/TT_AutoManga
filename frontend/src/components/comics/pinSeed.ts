/** Where a panel is in its .comic script, as comic.js --plan reports it (1-based lines). */
export interface PanelLines {
  line: number;             // the PANEL line
  seedLine: number | null;  // a "seed: N" key line in the panel, if it has one
}

/** Pin a panel's seed in the script text: rewrite its "seed:" line if it has one, else set (or replace)
    seed=N on its PANEL line. Throws when the lines no longer match (the text changed since the plan). */
export function pinSeed(text: string, panel: PanelLines, seed: number): string {
  const lines = text.split('\n');   // a "\r" stays on its line, so CRLF scripts keep their endings
  const keyLine = panel.seedLine != null ? lines[panel.seedLine - 1] : undefined;
  if (keyLine !== undefined && /^\s*seed\s*:/i.test(keyLine)) {
    lines[panel.seedLine! - 1] = keyLine.replace(/^(\s*seed\s*:\s*)[^\r]*/i, `$1${seed}`);
    return lines.join('\n');
  }
  const head = lines[panel.line - 1];
  if (head === undefined || !/^\s*PANEL\b/.test(head)) throw new Error(`line ${panel.line} is not a PANEL line any more`);
  const cr = head.endsWith('\r') ? '\r' : '';
  const body = head.slice(0, head.length - cr.length);
  lines[panel.line - 1] = (/(^|\s)seed=\S*/.test(body)
    ? body.replace(/(^|\s)seed=\S*/, `$1seed=${seed}`)
    : `${body.replace(/\s+$/, '')} seed=${seed}`) + cr;
  return lines.join('\n');
}

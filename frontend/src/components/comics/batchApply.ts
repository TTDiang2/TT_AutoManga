/** Batch AI rewrite (backend/api/comics_rewrite_batch.py): the job as the server reports it, and applying its
    accepted suggestions to the editor text. */

export type BatchStatus = 'running' | 'done' | 'stopped' | 'failed';
export type BatchResultStatus = 'pending' | 'running' | 'done' | 'failed' | 'refused';

export interface BatchResult {
  index: number;
  label: string;
  kind: string;
  start: number;            // UTF-16 offsets in the snapshot text
  end: number;
  status: BatchResultStatus;
  original: string;         // snapshot.slice(start, end)
  suggestion: string | null;
  plan: { ok: boolean; error: string | null; line: number | null } | null;
  error: string | null;
  durationMs: number | null;
  seq: number;
}

export interface Batch {
  id: string;
  script: string;
  action: string;
  instruction: string | null;
  kind: string;
  status: BatchStatus;
  error: string | null;
  model: string;
  startedAt: number;
  endedAt: number | null;
  snapshotHash: string;
  seq: number;
  total: number;
  done: number;
  failed: number;
  refused: number;
  results: BatchResult[];
  partial: boolean;         // results holds only those changed since the poll's `since`
}

/** FNV-1a (32 bit) over UTF-16 code units, with the length: the server's text_hash. */
export function textHash(text: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return `${text.length}:${h.toString(16).padStart(8, '0')}`;
}

/** A poll's answer merged into the batch held: a partial one replaces only the results it carries. */
export function mergeBatch(prev: Batch | null, next: Batch | null): Batch | null {
  if (!next) return null;
  if (!next.partial || !prev || prev.id !== next.id) return next;
  const byIndex = new Map(next.results.map(r => [r.index, r]));
  return { ...next, partial: false, results: prev.results.map(r => byIndex.get(r.index) ?? r) };
}

/** Results that ran: done, failed or refused. */
export const finished = (b: Batch) => b.done + b.failed + b.refused;

export type SkipReason = 'missing' | 'ambiguous' | 'overlap' | 'no-suggestion';

export interface ApplyReport {
  text: string;
  applied: number[];        // result indexes put in, in script order
  relocated: number[];      // of them, found away from their snapshot offsets
  skipped: { index: number; label: string; reason: SkipReason }[];
}

type Applicable = Pick<BatchResult, 'index' | 'label' | 'start' | 'end' | 'original' | 'suggestion'>;

/** Every place `needle` starts in text[from, to). */
function occurrences(text: string, needle: string, from = 0, to = text.length): number[] {
  const out: number[] = [];
  if (!needle) return out;
  for (let i = text.indexOf(needle, from); i !== -1 && i + needle.length <= to; i = text.indexOf(needle, i + 1)) out.push(i);
  return out;
}

const toLf = (s: string) => s.replace(/\r\n/g, '\n');
const toCrlf = (s: string) => toLf(s).replace(/\n/g, '\r\n');

/** Put the accepted suggestions into `text` (the editor's text now). Each block is put back where its original
    still is: at its snapshot offsets when the text there is unchanged, else found by exact search within
    `window` characters of them, else anywhere, when it occurs exactly once (also with the editor's line endings,
    should they differ from the snapshot's). A block found nowhere, or more than once, or overlapping one already
    placed, is skipped and reported. Blocks are applied from the last to the first, so offsets stay valid. */
export function applyAccepted(text: string, results: Applicable[], window = 2000): ApplyReport {
  const crlf = text.includes('\r\n');
  const placed: { r: Applicable; at: number; original: string; suggestion: string; moved: boolean }[] = [];
  const skipped: ApplyReport['skipped'] = [];
  for (const r of results) {
    if (r.suggestion == null) { skipped.push({ index: r.index, label: r.label, reason: 'no-suggestion' }); continue; }
    if (text.slice(r.start, r.end) === r.original) {
      placed.push({ r, at: r.start, original: r.original, suggestion: r.suggestion, moved: false });
      continue;
    }
    // the editor's line endings (a textarea edit turns CRLF into LF)
    const original = crlf ? toCrlf(r.original) : toLf(r.original);
    const suggestion = crlf ? toCrlf(r.suggestion) : toLf(r.suggestion);
    const near = occurrences(text, original, Math.max(0, r.start - window), Math.min(text.length, r.end + window));
    const hits = near.length ? near : occurrences(text, original);
    if (hits.length !== 1) {
      skipped.push({ index: r.index, label: r.label, reason: hits.length ? 'ambiguous' : 'missing' });
      continue;
    }
    placed.push({ r, at: hits[0], original, suggestion, moved: true });
  }
  // last first; one that reaches into a block already placed is skipped
  placed.sort((a, b) => b.at - a.at);
  let out = text;
  let limit = Infinity;
  const applied: number[] = [];
  const relocated: number[] = [];
  for (const p of placed) {
    if (p.at + p.original.length > limit) { skipped.push({ index: p.r.index, label: p.r.label, reason: 'overlap' }); continue; }
    out = out.slice(0, p.at) + p.suggestion + out.slice(p.at + p.original.length);
    limit = p.at;
    applied.unshift(p.r.index);
    if (p.moved) relocated.unshift(p.r.index);
  }
  skipped.sort((a, b) => a.index - b.index);
  return { text: out, applied, relocated, skipped };
}

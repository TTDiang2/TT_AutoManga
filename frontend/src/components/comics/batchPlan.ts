/** Batch AI dialog: the blocks a batch would rewrite (from the script's outline), and how long it may take. */

import { findBlock } from './aiBlock';
import { entryLabel, listOf, parseOutline, targetLabel, type OutlineKind, type OutlineWords } from './outline';

export interface BatchCandidate {
  id: string;              // the outline entry's id ("s3", "2", "2.3")
  kind: OutlineKind;
  start: number;
  end: number;
  label: string;           // as the outline lists it ("Cafe, morning · 2.1–3.4")
  fullLabel: string;       // with its kind ("Scene: Cafe, morning · 2.1–3.4"), sent to the server
  uncut: boolean;          // every line inside a PAGE uncut / PANEL uncut block, as the server checks it
  todo: boolean;
}

export type BatchScope = 'all' | 'uncut' | 'chosen';

/** The blocks of `kind` in `text`, in script order (blank ones left out). Computed from the very text that is
    sent, so the server's offsets match. */
export function batchCandidates(text: string, kind: OutlineKind, words: OutlineWords): BatchCandidate[] {
  const outline = parseOutline(text);
  const out: BatchCandidate[] = [];
  for (const e of listOf(outline, kind)) {
    const b = findBlock(text, e.startOffset, e.endOffset);
    if (!b) continue;
    out.push({
      id: e.id, kind, start: e.startOffset, end: e.endOffset, label: entryLabel(kind, e, words),
      fullLabel: targetLabel({ kind, start: e.startOffset, end: e.endOffset, entry: e }, words),
      uncut: b.uncut, todo: b.todo || e.todo,
    });
  }
  return out;
}

/** The candidates a scope picks: all, the uncut ones, or the chosen ids. */
export function chooseBlocks(cands: BatchCandidate[], scope: BatchScope, chosen: ReadonlySet<string>): BatchCandidate[] {
  if (scope === 'uncut') return cands.filter(c => c.uncut);
  if (scope === 'chosen') return cands.filter(c => chosen.has(c.id));
  return cands;
}

/** Draft uncut scene is offered only when every block is an uncut block. */
export const draftUncutAllowed = (blocks: BatchCandidate[]) => blocks.length > 0 && blocks.every(b => b.uncut);

export const SECONDS_PER_BLOCK = 30;

/** "~N blocks · ~M min": minutes rounded up, at least 1 when there is anything to do. */
export function estimate(blocks: number, secondsPerBlock = SECONDS_PER_BLOCK) {
  return { blocks, minutes: blocks > 0 ? Math.max(1, Math.ceil((blocks * secondsPerBlock) / 60)) : 0, secondsPerBlock };
}

/** The request body's block list. */
export const requestBlocks = (blocks: BatchCandidate[]) =>
  blocks.map(b => ({ start: b.start, end: b.end, label: b.fullLabel, kind: b.kind }));

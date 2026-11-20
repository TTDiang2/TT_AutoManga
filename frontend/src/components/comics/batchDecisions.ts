import { create } from 'zustand';
import type { BatchResult } from './batchApply';

/** The owner's Accept / Reject choices on a batch's suggestions, and which were applied, by batch id. Kept in a
    store (they survive tab switches) and in localStorage when it works (a reload; else they are lost, which is
    fine: the suggestions themselves are on the server). */
export type Decision = 'accept' | 'reject';

interface Review {
  decisions: Record<string, Record<number, Decision>>;
  applied: Record<string, number[]>;
  decide: (batch: string, indexes: number[], d: Decision | null) => void;
  markApplied: (batch: string, indexes: number[]) => void;
  forget: (batch: string) => void;
}

const KEY = 'automanga.comics.batch.review';
const KEEP = 5;   // batches remembered

function load(): Pick<Review, 'decisions' | 'applied'> {
  try {
    const raw = window.localStorage.getItem(KEY);
    const v = raw ? JSON.parse(raw) : null;
    if (v && typeof v === 'object' && v.decisions && v.applied) return { decisions: v.decisions, applied: v.applied };
  } catch { /* none kept */ }
  return { decisions: {}, applied: {} };
}

function keep<T>(rec: Record<string, T>, id: string, value: T): Record<string, T> {
  const next = { ...rec };
  delete next[id];
  next[id] = value;   // newest last
  const ids = Object.keys(next);
  for (const old of ids.slice(0, Math.max(0, ids.length - KEEP))) delete next[old];
  return next;
}

export const useBatchReview = create<Review>()((set) => ({
  ...(typeof window !== 'undefined' ? load() : { decisions: {}, applied: {} }),
  decide: (batch, indexes, d) => set((s) => {
    const cur = { ...(s.decisions[batch] ?? {}) };
    for (const i of indexes) { if (d) cur[i] = d; else delete cur[i]; }
    return { decisions: keep(s.decisions, batch, cur) };
  }),
  markApplied: (batch, indexes) => set((s) => ({
    applied: keep(s.applied, batch, [...new Set([...(s.applied[batch] ?? []), ...indexes])]),
  })),
  forget: (batch) => set((s) => {
    const decisions = { ...s.decisions }, applied = { ...s.applied };
    delete decisions[batch]; delete applied[batch];
    return { decisions, applied };
  }),
}));

useBatchReview.subscribe((s) => {
  try { window.localStorage.setItem(KEY, JSON.stringify({ decisions: s.decisions, applied: s.applied })); } catch { /* not kept */ }
});

export type BatchFilter = 'all' | 'passing' | 'flagged' | 'failed' | 'refused';

export const passing = (r: BatchResult) => r.status === 'done' && !!r.plan?.ok;
export const flagged = (r: BatchResult) => r.status === 'done' && !r.plan?.ok;

export function filterResults(results: BatchResult[], f: BatchFilter): BatchResult[] {
  if (f === 'passing') return results.filter(passing);
  if (f === 'flagged') return results.filter(flagged);
  if (f === 'failed') return results.filter(r => r.status === 'failed');
  if (f === 'refused') return results.filter(r => r.status === 'refused');
  return results;
}

/** Accepted, done and not applied yet: what "Apply N accepted" puts in. */
export function toApply(results: BatchResult[], decisions: Record<number, Decision> | undefined, applied: number[] | undefined) {
  const done = new Set(applied ?? []);
  return results.filter(r => r.status === 'done' && r.suggestion != null && decisions?.[r.index] === 'accept' && !done.has(r.index));
}

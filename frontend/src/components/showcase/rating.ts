/** Content rating in the Showcase: a project's effective rating, which covers
    are blurred, and the per-session reveal of mature covers (unit-tested). */
import { useSyncExternalStore } from 'react';
import type { ContentRating } from '../../types';

/** A project's rating: its settings.contentRating, else the global default. */
export function effectiveRating(settings: { contentRating?: unknown } | null | undefined,
  fallback: ContentRating): ContentRating {
  const r = String(settings?.contentRating ?? '').toLowerCase();
  return r === 'mature' || r === 'sfw' ? r : fallback;
}

/** The names of the mature episodes (for the collection export notice). */
export function matureNames(episodes: readonly { name: string; contentRating?: string }[]): string[] {
  return episodes.filter(e => e.contentRating === 'mature').map(e => e.name);
}

// mature covers the viewer clicked to show, for this browser session only
const KEY = 'automanga.revealedMature';
const listeners = new Set<() => void>();

function readRevealed(): ReadonlySet<string> {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    const v: unknown = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []);
  } catch {
    return new Set();
  }
}

let revealed: ReadonlySet<string> = readRevealed();

export function isRevealed(id: string): boolean {
  return revealed.has(id);
}

export function revealMature(id: string): void {
  if (revealed.has(id)) return;
  revealed = new Set([...revealed, id]);
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify([...revealed]));
  } catch {
    // private mode / blocked storage: revealed for this page view only
  }
  listeners.forEach(l => l());
}

/** Test hook: forget every reveal. */
export function resetRevealed(): void {
  revealed = new Set();
  try { window.sessionStorage.removeItem(KEY); } catch { /* ignore */ }
  listeners.forEach(l => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => { listeners.delete(l); };
}

/** The set of revealed project ids (re-renders when one is revealed). */
export function useRevealedMature(): ReadonlySet<string> {
  return useSyncExternalStore(subscribe, () => revealed, () => revealed);
}

/** Pure helpers for the Showcase collections view (unit-tested). */

export interface CollectionEpisode {
  id: string;
  name: string;
  pages: number;
  firstPageId: string | null;
  cover: string | null;
  updatedAt?: string;
}

export interface Collection {
  id: string;
  name: string;
  description?: string;
  projectIds: string[];
  cover: { projectId: string; pageId: string | null } | null;
  auto?: boolean;
  createdAt: string;
  updatedAt: string;
  episodes: CollectionEpisode[];
  missing: string[];
  pages: number;
  coverUrl: string | null;
}

export interface CollectionExportJob {
  id: string;
  collectionId: string;
  status: 'running' | 'done' | 'error';
  done: number;
  total: number;
  error: string | null;
  warnings: string[];
  pdf: { url: string; name: string } | null;
  zip: { url: string; name: string } | null;
}

/** Move the item at `from` to `to` (a new array; out-of-range moves are no-ops). */
export function moveItem<T>(list: readonly T[], from: number, to: number): T[] {
  const out = list.slice();
  if (from < 0 || from >= out.length || to < 0 || to >= out.length || from === to) return out;
  const [item] = out.splice(from, 1);
  out.splice(to, 0, item);
  return out;
}

/** Episode ids after adding `added` (appended in the given order, no duplicates). */
export function addEpisodes(ids: readonly string[], added: readonly string[]): string[] {
  const out = ids.slice();
  for (const id of added) if (!out.includes(id)) out.push(id);
  return out;
}

/**
 * The episode's own title within its collection: "Episode 1 — The Rainy Gym"
 * for "Jade & Haile — Episode 1 — The Rainy Gym" in "Jade & Haile" (the
 * separators the backend's auto-group accepts: em dash, " – ", " - ").
 */
export function episodeTitle(collectionName: string, projectName: string): string {
  const name = projectName.trim();
  const m = /\s*—\s*|\s+[–-]\s+/.exec(name);
  if (!m || m.index === 0) return name;
  const base = name.slice(0, m.index).trim();
  const rest = name.slice(m.index + m[0].length).trim();
  return base === collectionName.trim() && rest ? rest : name;
}

/** Whole-number percentage of an export job (0 while the total is unknown). */
export function exportPercent(job: Pick<CollectionExportJob, 'done' | 'total'> | null): number {
  if (!job || job.total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((job.done / job.total) * 100)));
}

/** Clamp an export scale to the backend's bounds (0.5-8); NaN falls back to 2. */
export function clampScale(v: number): number {
  if (!Number.isFinite(v)) return 2;
  return Math.min(8, Math.max(0.5, v));
}

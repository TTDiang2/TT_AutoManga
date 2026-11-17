/** Uploading .comic files to the Comics repo (POST /api/comics/scripts/upload). */
import { fill } from '../../hooks/useTranslation';

export interface UploadResult {
  file: string;
  name: string | null;
  status: 'saved' | 'replaced' | 'exists' | 'busy' | 'invalid';
  error?: string;
  plan?: { ok: boolean; error: string | null; line: number | null };
}

export interface UploadWords { uploadDone: string; uploadSkipped: string; uploadCheck: string }

export async function postUpload(files: File[], overwrite: boolean): Promise<UploadResult[]> {
  const fd = new FormData();
  files.forEach(f => fd.append('files', f));
  fd.append('overwrite', String(overwrite));
  const res = await fetch('/api/comics/scripts/upload', { method: 'POST', body: fd });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
  return body.results as UploadResult[];
}

export const uploaded = (r: UploadResult) => r.status === 'saved' || r.status === 'replaced';

/** Files that are only .comic/.txt by name: the rest is reported by the server too, but a folder or an image
    dropped by mistake needn't be sent. */
export const comicFiles = (files: Iterable<File>) => [...files].filter(f => /\.(comic|txt)$/i.test(f.name));

/** One line for the notice: what was added, what was kept, what failed and which saved scripts have errors. */
export function uploadSummary(results: UploadResult[], w: UploadWords): { text: string; warn: boolean } {
  const parts: string[] = [];
  const done = results.filter(uploaded);
  if (done.length) parts.push(fill(w.uploadDone, { n: done.map(r => `${r.name}.comic`).join(', ') }));
  const kept = results.filter(r => r.status === 'exists');
  if (kept.length) parts.push(fill(w.uploadSkipped, { names: kept.map(r => `${r.name}.comic`).join(', ') }));
  for (const r of results) {
    if (r.status === 'invalid' || r.status === 'busy') parts.push(`${r.file}: ${r.error}`);
    else if (uploaded(r) && r.plan && !r.plan.ok)
      parts.push(fill(w.uploadCheck, { name: `${r.name}.comic`, line: r.plan.line ?? '?', error: (r.plan.error ?? '').replace(/^.*?\.comic:\d+:\s*/, '') }));
  }
  const warn = results.some(r => !uploaded(r) || (r.plan && !r.plan.ok));
  return { text: parts.join(' · '), warn };
}

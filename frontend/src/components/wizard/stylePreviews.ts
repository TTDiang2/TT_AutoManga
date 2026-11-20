import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import type { PromptFormat } from './wizardLogic';

/**
 * Art-style previews for the wizard's Look step: one small picture per style,
 * drawn with the user's own SwarmUI model from the same scene and seed, so
 * the styles can be compared. Cached per model, prompt format and style text
 * in this browser; a cached picture whose asset has gone (the startup cleanup
 * removes unreferenced assets after some weeks) is simply drawn again.
 */

export const PREVIEW_SEED = 424242;

/** The same scene for every style; only the style text changes. */
export function previewPrompt(format: PromptFormat, style: string): string {
  const s = style.trim();
  return format === 'prose'
    ? `A young traveler holding a paper umbrella stands on an old stone bridge in the rain, full body, a single illustration.${s ? ` Style: ${s}.` : ''}`
    : `1girl, solo, traveler, holding umbrella, paper umbrella, stone bridge, rain, river, full body${s ? `, ${s}` : ''}`;
}

export function previewKey(model: string, format: PromptFormat, style: string): string {
  return `${model || '(default model)'}|${format}|${style.trim().toLowerCase()}`;
}

interface JobSnapshot {
  status: string;
  items: { index: number; status: string; result?: { assets?: { url: string }[] } | null; error?: string | null }[];
}

export interface PreviewState {
  images: Record<string, string>;     // key → asset URL (persisted)
  pending: Record<string, true>;
  errors: Record<string, string>;
  /** Draw these previews (keys already pending are skipped). */
  draw: (jobs: { key: string; prompt: string }[], opts: { format: PromptFormat; projectId?: string | null }) => Promise<void>;
  /** Drop a cached picture (e.g. its file is gone). */
  forget: (key: string) => void;
}

const POLL_MS = 2500;

export const useStylePreviews = create<PreviewState>()(
  persist(
    (set, get) => ({
      images: {},
      pending: {},
      errors: {},

      forget: key => set(s => {
        const images = { ...s.images };
        delete images[key];
        return { images };
      }),

      draw: async (jobs, { format, projectId }) => {
        const todo = jobs.filter(j => !get().pending[j.key]);
        if (!todo.length) return;
        const mark = (keys: string[], on: boolean) => set(s => {
          const pending = { ...s.pending };
          const errors = { ...s.errors };
          for (const k of keys) {
            if (on) { pending[k] = true; delete errors[k]; } else delete pending[k];
          }
          return { pending, errors };
        });
        const fail = (keys: string[], msg: string) => {
          mark(keys, false);
          set(s => ({ errors: { ...s.errors, ...Object.fromEntries(keys.map(k => [k, msg])) } }));
        };
        mark(todo.map(j => j.key), true);

        let jobId: string;
        try {
          const res = await fetch('/api/agent/generate-batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              // the project only decides the content rating; nothing is
              // injected into the prompt and nothing is bound to a panel
              project_id: projectId || undefined,
              concurrency: 1,
              jobs: todo.map(j => ({
                prompt: j.prompt, seed: PREVIEW_SEED, prompt_format: format,
                apply_to_panel: false, inject_characters: false,
              })),
            }),
          });
          const data = await res.json().catch(() => ({}));
          if (!res.ok || !data.job_id) throw new Error(data.detail || `HTTP ${res.status}`);
          jobId = data.job_id;
        } catch (e) {
          fail(todo.map(j => j.key), String((e as Error).message || e));
          return;
        }

        const settled = new Set<number>();
        for (;;) {
          await new Promise(r => setTimeout(r, POLL_MS));
          let snap: JobSnapshot;
          try {
            const r = await fetch(`/api/agent/jobs/${jobId}`);
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            snap = await r.json();
          } catch {
            // the job table is gone (server restart): give up on the rest
            fail(todo.filter((_, i) => !settled.has(i)).map(j => j.key), 'The server restarted; try again');
            return;
          }
          for (const item of snap.items) {
            if (settled.has(item.index)) continue;
            const key = todo[item.index]?.key;
            if (!key) continue;
            const url = item.result?.assets?.[0]?.url;
            if (item.status === 'done' && url) {
              settled.add(item.index);
              mark([key], false);
              set(s => ({ images: { ...s.images, [key]: url } }));
            } else if (item.status === 'error' || item.status === 'done') {
              settled.add(item.index);
              fail([key], item.error || 'No picture came back');
            }
          }
          if (snap.status === 'done' || settled.size === todo.length) return;
        }
      },
    }),
    {
      name: 'automanga-style-previews',
      storage: createJSONStorage(() => localStorage),
      partialize: s => ({ images: s.images }),
    },
  ),
);

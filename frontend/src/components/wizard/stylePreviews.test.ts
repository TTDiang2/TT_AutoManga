import { afterEach, describe, expect, it, vi } from 'vitest';
import { PREVIEW_SEED, previewKey, previewPrompt, useStylePreviews } from './stylePreviews';

describe('previewPrompt', () => {
  it('uses the same scene for every style, in the chosen prompt format', () => {
    expect(previewPrompt('danbooru', ' noir comic ')).toBe(
      '1girl, solo, traveler, holding umbrella, paper umbrella, stone bridge, rain, river, full body, noir comic');
    expect(previewPrompt('prose', 'watercolor')).toMatch(/stone bridge in the rain.*Style: watercolor\.$/);
    expect(previewPrompt('danbooru', '')).not.toMatch(/,\s*$/);
  });
});

describe('previewKey', () => {
  it('separates models and formats, ignores case and spacing of the style', () => {
    expect(previewKey('m1', 'danbooru', ' Noir ')).toBe(previewKey('m1', 'danbooru', 'noir'));
    expect(previewKey('m1', 'danbooru', 'noir')).not.toBe(previewKey('m2', 'danbooru', 'noir'));
    expect(previewKey('m1', 'danbooru', 'noir')).not.toBe(previewKey('m1', 'prose', 'noir'));
  });
});

describe('draw', () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); useStylePreviews.setState({ images: {}, pending: {}, errors: {} }); });

  it('sends one batch with a fixed seed and no injection, then stores each picture or error', async () => {
    vi.useFakeTimers();
    const calls: { url: string; body?: unknown }[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (url === '/api/agent/generate-batch') return new Response(JSON.stringify({ job_id: 'j1', total: 2 }), { status: 202 });
      return new Response(JSON.stringify({
        status: 'done',
        items: [
          { index: 0, status: 'done', result: { assets: [{ url: '/api/assets/file/a1' }] } },
          { index: 1, status: 'error', error: 'SwarmUI: out of memory' },
        ],
      }));
    }));
    const p = useStylePreviews.getState().draw(
      [{ key: 'k1', prompt: 'p1' }, { key: 'k2', prompt: 'p2' }], { format: 'danbooru', projectId: 'proj' });
    expect(useStylePreviews.getState().pending).toEqual({ k1: true, k2: true });
    await vi.advanceTimersByTimeAsync(3000);
    await p;
    const body = calls[0].body as { project_id: string; jobs: Record<string, unknown>[] };
    expect(body.project_id).toBe('proj');
    expect(body.jobs[0]).toMatchObject({ prompt: 'p1', seed: PREVIEW_SEED, apply_to_panel: false, inject_characters: false });
    const s = useStylePreviews.getState();
    expect(s.images).toEqual({ k1: '/api/assets/file/a1' });
    expect(s.errors).toEqual({ k2: 'SwarmUI: out of memory' });
    expect(s.pending).toEqual({});
  });

  it('marks every job failed when the batch is refused', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'job 0: refused' }), { status: 400 })));
    await useStylePreviews.getState().draw([{ key: 'k1', prompt: 'p1' }], { format: 'prose' });
    expect(useStylePreviews.getState().errors).toEqual({ k1: 'job 0: refused' });
    expect(useStylePreviews.getState().pending).toEqual({});
  });
});

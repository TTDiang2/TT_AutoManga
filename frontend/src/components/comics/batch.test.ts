import { describe, it, expect } from 'vitest';
import { applyAccepted, mergeBatch, textHash, type Batch, type BatchResult } from './batchApply';
import { batchCandidates, chooseBlocks, draftUncutAllowed, estimate, requestBlocks } from './batchPlan';
import { filterResults, toApply } from './batchDecisions';
import type { OutlineWords } from './outline';

const WORDS: OutlineWords = { page: 'Page {n}', uncutPage: 'Uncut page {n}', noPlace: 'No place', panel: 'Panel', scene: 'Scene' };

const SCRIPT = [
  'title: T',                 // 1
  '',
  'PAGE',                     // 3
  'PANEL',
  'place: cafe, day',
  'KIM: one',
  '',
  'PANEL',                    // 8
  'KIM: two',
  '',
  'PAGE',                     // 11
  'PANEL',
  'place: roof, night',
  'KIM: three',
  '',
  'PAGE uncut todo',          // 16
  'PANEL',
  'place: room, night',
  '// TODO',
  '',
].join('\n');

const res = (index: number, text: string, original: string, suggestion: string | null, label = `b${index}`): BatchResult => {
  const start = text.indexOf(original);
  return { index, label, kind: 'panel', start, end: start + original.length, status: 'done', original, suggestion,
    plan: { ok: true, error: null, line: null }, error: null, durationMs: 1, seq: 1 };
};

describe('applyAccepted', () => {
  const a = 'PANEL\nplace: cafe, day\nKIM: one\n\n';
  const b = 'PANEL\nKIM: two\n\n';
  const c = 'PANEL\nplace: roof, night\nKIM: three\n\n';

  it('applies bottom-up so earlier offsets stay valid', () => {
    const rs = [res(0, SCRIPT, a, 'PANEL\nplace: cafe, day\nKIM: a much longer first line now\n\n'),
      res(1, SCRIPT, b, 'PANEL\nKIM: 2\n\n'), res(2, SCRIPT, c, 'PANEL\nplace: roof, night\nKIM: 3!\n\n')];
    const out = applyAccepted(SCRIPT, rs);
    expect(out.applied).toEqual([0, 1, 2]);
    expect(out.skipped).toEqual([]);
    expect(out.relocated).toEqual([]);
    expect(out.text).toContain('KIM: a much longer first line now\n\nPANEL\nKIM: 2\n\nPAGE\nPANEL\nplace: roof, night\nKIM: 3!');
    expect(out.text.startsWith('title: T\n\nPAGE\n')).toBe(true);
    expect(out.text.endsWith('// TODO\n')).toBe(true);
  });

  it('finds blocks again in drifted text (near their offsets, then anywhere unique)', () => {
    const rs = [res(0, SCRIPT, a, 'A\n'), res(2, SCRIPT, c, 'C\n')];
    // typed above the blocks: everything shifted by 3000 characters (beyond the near window for the search)
    const drifted = SCRIPT.replace('title: T\n', `title: T\n// ${'x'.repeat(3000)}\n`);
    const out = applyAccepted(drifted, rs);
    expect(out.applied).toEqual([0, 2]);
    expect(out.relocated).toEqual([0, 2]);
    expect(out.text).toContain('\nPAGE\nA\nPANEL\nKIM: two\n\nPAGE\nC\nPAGE uncut todo');
  });

  it('skips originals that changed, or occur more than once', () => {
    const rs = [res(0, SCRIPT, a, 'A\n'), res(1, SCRIPT, b, 'B\n'), res(2, SCRIPT, c, 'C\n')];
    // block 0 edited by hand; block 1 duplicated far away (twice in the text, away from its offsets)
    let edited = SCRIPT.replace('KIM: one', 'KIM: uno');
    edited = edited.replace('title: T\n', `title: T\n// ${'y'.repeat(50)}\n`) + 'PAGE\n' + b + '\n'.repeat(3000) + 'PAGE\n' + b;
    const out = applyAccepted(edited, rs, 20);
    expect(out.applied).toEqual([2]);
    expect(out.skipped).toEqual([{ index: 0, label: 'b0', reason: 'missing' }, { index: 1, label: 'b1', reason: 'ambiguous' }]);
    expect(out.text).toContain('\nPAGE\nC\nPAGE uncut');
    expect(out.text).toContain('KIM: uno');
  });

  it('a block found twice near its offset is ambiguous too', () => {
    const t = 'PAGE\nPANEL\nX\n\nPANEL\nX\n\n';
    const r = { ...res(0, t, 'PANEL\nX\n\n', 'Y\n'), start: 1, end: 2 };   // stale offsets
    expect(applyAccepted(t, [r]).skipped[0].reason).toBe('ambiguous');
  });

  it('skips overlapping placements and missing suggestions', () => {
    const t = 'PAGE\nPANEL\nA\n\nPANEL\nB\n';
    const whole = res(0, t, 'PANEL\nA\n\nPANEL\nB\n', 'W\n');
    const inner = res(1, t, 'PANEL\nB\n', 'I\n');
    const none = { ...res(2, t, 'PAGE\n', null) };
    const out = applyAccepted(t, [whole, inner, none]);
    expect(out.applied).toEqual([1]);
    expect(out.skipped.map(s => [s.index, s.reason])).toEqual([[0, 'overlap'], [2, 'no-suggestion']]);
  });

  it('keeps CRLF text CRLF, and finds CRLF originals in text the textarea turned to LF', () => {
    const crlf = SCRIPT.replace(/\n/g, '\r\n');
    const orig = 'PANEL\r\nKIM: two\r\n\r\n';
    const r = res(1, crlf, orig, 'PANEL\r\nKIM: 2\r\n\r\n');
    const same = applyAccepted(crlf, [r]);
    expect(same.applied).toEqual([1]);
    expect(same.text).toBe(crlf.replace('KIM: two', 'KIM: 2'));
    // the editor normalised line endings: found by its LF form, put in as LF
    const lf = applyAccepted(SCRIPT, [r]);
    expect(lf.applied).toEqual([1]);
    expect(lf.relocated).toEqual([1]);
    expect(lf.text).toBe(SCRIPT.replace('KIM: two', 'KIM: 2'));
    expect(lf.text.includes('\r')).toBe(false);
    // and the other way round: an LF snapshot, a CRLF editor text
    const r2 = res(1, SCRIPT, 'PANEL\nKIM: two\n\n', 'PANEL\nKIM: 2\n\n');
    const back = applyAccepted(crlf, [r2]);
    expect(back.text).toBe(crlf.replace('KIM: two', 'KIM: 2'));
  });
});

describe('textHash and mergeBatch', () => {
  it('hashes like the server (FNV-1a over UTF-16 units, with the length)', () => {
    // backend/api/comics_rewrite_batch.py text_hash: the same values (checked there by hand)
    expect(textHash('')).toBe('0:811c9dc5');
    expect(textHash('a')).toBe('1:e40c292c');
    expect(textHash('PAGE\n😀')).toBe('7:fbf9b471');   // a surrogate pair: two units
    expect(textHash('ab')).not.toBe(textHash('ba'));
  });

  it('merges a partial poll by index', () => {
    const base = { id: 'x', partial: false, results: [res(0, 'ab', 'a', 'A'), res(1, 'ab', 'b', null)] } as unknown as Batch;
    const changed = { ...res(1, 'ab', 'b', 'B'), status: 'done' as const };
    const next = { id: 'x', partial: true, results: [changed], done: 2 } as unknown as Batch;
    const m = mergeBatch(base, next)!;
    expect(m.results.map(r => r.suggestion)).toEqual(['A', 'B']);
    expect(m.partial).toBe(false);
    const other = { id: 'y', partial: true, results: [] } as unknown as Batch;
    expect(mergeBatch(base, other)).toBe(other);
    expect(mergeBatch(base, null)).toBeNull();
  });
});

describe('batch blocks, scope and estimate', () => {
  it('lists scenes, pages and panels with the server-side uncut check', () => {
    const scenes = batchCandidates(SCRIPT, 'scene', WORDS);
    expect(scenes.map(s => s.label)).toEqual(['Cafe, day · 1.1–1.2', 'Roof, night · 2.1', 'Room, night · u1.1']);
    expect(scenes.map(s => s.uncut)).toEqual([false, false, true]);
    expect(scenes[2].todo).toBe(true);
    const pages = batchCandidates(SCRIPT, 'page', WORDS);
    expect(pages.map(p => p.id)).toEqual(['1', '2', 'u1']);
    const panels = batchCandidates(SCRIPT, 'panel', WORDS);
    expect(panels.map(p => p.id)).toEqual(['1.1', '1.2', '2.1', 'u1.1']);
    // sorted, non-overlapping, each block's text the script's
    for (let i = 1; i < panels.length; i++) expect(panels[i].start).toBeGreaterThanOrEqual(panels[i - 1].end);
    expect(SCRIPT.slice(panels[1].start, panels[1].end)).toBe('PANEL\nKIM: two\n\n');
    expect(requestBlocks(panels.slice(0, 1))).toEqual([{ start: panels[0].start, end: panels[0].end, label: 'Panel 1.1', kind: 'panel' }]);
  });

  it('picks all, uncut only, or the chosen ones (in script order)', () => {
    const panels = batchCandidates(SCRIPT, 'panel', WORDS);
    expect(chooseBlocks(panels, 'all', new Set()).length).toBe(4);
    expect(chooseBlocks(panels, 'uncut', new Set()).map(p => p.id)).toEqual(['u1.1']);
    expect(chooseBlocks(panels, 'chosen', new Set(['2.1', '1.1', 'gone'])).map(p => p.id)).toEqual(['1.1', '2.1']);
    expect(chooseBlocks(panels, 'chosen', new Set()).length).toBe(0);
  });

  it('offers Draft uncut only when every block is uncut', () => {
    const panels = batchCandidates(SCRIPT, 'panel', WORDS);
    expect(draftUncutAllowed(panels)).toBe(false);
    expect(draftUncutAllowed(chooseBlocks(panels, 'uncut', new Set()))).toBe(true);
    expect(draftUncutAllowed([])).toBe(false);
  });

  it('estimates at ~30 s per block, rounded up', () => {
    expect(estimate(0)).toEqual({ blocks: 0, minutes: 0, secondsPerBlock: 30 });
    expect(estimate(1).minutes).toBe(1);
    expect(estimate(3).minutes).toBe(2);
    expect(estimate(30).minutes).toBe(15);
    expect(estimate(10, 45).minutes).toBe(8);
  });
});

describe('review filters', () => {
  const t = 'abcdef';
  const ok = res(0, t, 'a', 'A');
  const bad = { ...res(1, t, 'b', 'B'), plan: { ok: false, error: 'x', line: 1 } };
  const failed = { ...res(2, t, 'c', null), status: 'failed' as const };
  const refused = { ...res(3, t, 'd', null), status: 'refused' as const };
  const pending = { ...res(4, t, 'e', null), status: 'pending' as const };
  const all = [ok, bad, failed, refused, pending];

  it('filters by outcome', () => {
    expect(filterResults(all, 'all').length).toBe(5);
    expect(filterResults(all, 'passing')).toEqual([ok]);
    expect(filterResults(all, 'flagged')).toEqual([bad]);
    expect(filterResults(all, 'failed')).toEqual([failed]);
    expect(filterResults(all, 'refused')).toEqual([refused]);
  });

  it('applies accepted, done, not yet applied ones only', () => {
    const d = { 0: 'accept', 1: 'accept', 2: 'accept', 3: 'reject' } as const;
    expect(toApply(all, d, []).map(r => r.index)).toEqual([0, 1]);
    expect(toApply(all, d, [0]).map(r => r.index)).toEqual([1]);
    expect(toApply(all, undefined, undefined)).toEqual([]);
  });
});

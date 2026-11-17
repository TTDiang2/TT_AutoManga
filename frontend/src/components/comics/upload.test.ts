import { describe, expect, it } from 'vitest';
import { comicFiles, uploadSummary, type UploadResult } from './comicsUpload';

const w = { uploadDone: 'Uploaded {n}', uploadSkipped: 'kept the existing {names}', uploadCheck: '{name}: line {line}: {error}' };

describe('uploadSummary', () => {
  it('lists what was added, kept and failed', () => {
    const r: UploadResult[] = [
      { file: 'A.comic', name: 'a', status: 'saved', plan: { ok: true, error: null, line: null } },
      { file: 'b.comic', name: 'b', status: 'replaced', plan: { ok: false, error: '/x/scripts/b.comic:3: unknown character "zork"', line: 3 } },
      { file: 'c.comic', name: 'c', status: 'exists', error: 'c.comic already exists' },
      { file: 'd.png', name: null, status: 'invalid', error: 'not a .comic file' },
    ];
    expect(uploadSummary(r, w)).toEqual({
      text: 'Uploaded a.comic, b.comic · kept the existing c.comic · b.comic: line 3: unknown character "zork" · d.png: not a .comic file',
      warn: true,
    });
  });
  it('is not a warning when everything saved cleanly', () => {
    expect(uploadSummary([{ file: 'a.comic', name: 'a', status: 'saved', plan: { ok: true, error: null, line: null } }], w))
      .toEqual({ text: 'Uploaded a.comic', warn: false });
  });
});

describe('comicFiles', () => {
  it('keeps .comic and .txt files only', () => {
    const f = (n: string) => new File(['x'], n);
    expect(comicFiles([f('a.comic'), f('B.COMIC'), f('c.txt'), f('d.png')]).map(x => x.name)).toEqual(['a.comic', 'B.COMIC', 'c.txt']);
  });
});
